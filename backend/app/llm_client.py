import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import httpx
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger("app.llm_client")


async def call_lm_studio(prompt_messages: List[Dict[str, str]], response_format_schema: Any = None) -> Dict[str, Any]:
    """
    Direct low-latency route utility to LM Studio.
    Forces strict JSON outputs using custom parameters, staying within MacBook memory parameters.
    """
    headers = {
        "Authorization": f"Bearer {settings.LM_STUDIO_API_KEY}",
        "Content-Type": "application/json"
    }

    # Configure request payload staying strictly inside context window memory budgets
    payload: Dict[str, Any] = {
        "model": settings.LM_STUDIO_MODEL_FALLBACK,
        "messages": prompt_messages,
        "temperature": settings.TEMPERATURE,
        "max_tokens": 1500,  # Retain safe generation budget within the 8192 limit
        "stream": False
    }

    # If schema is specified, request structured output constraints from LM Studio JSON mode
    if response_format_schema:
        payload["response_format"] = {
            "type": "json_object",
            "schema": response_format_schema.model_json_schema()
        }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info(f"Dispatching inference task to local LM Studio at {settings.LM_STUDIO_URL}")
            response = await client.post(
                f"{settings.LM_STUDIO_URL}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()

            # Access response text safely
            content_text = result["choices"][0]["message"]["content"]
            logger.info("Successfully fetched response from local LLM.")
            return json.loads(content_text) if response_format_schema else {"text": content_text}

    except httpx.HTTPStatusError as http_err:
        logger.error(f"LM Studio server returned status error: {http_err.response.status_code} - {http_err.response.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Inference gateway error: {str(http_err)}"
        )
    except httpx.RequestError as req_err:
        logger.error(f"Failed to connect to local LM Studio instance: {str(req_err)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LM Studio is offline or unavailable. Ensure it runs on localhost:1234 with API keys."
        )
    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to parse LLM structured output block: {str(json_err)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Local LLM output failed to resolve as a valid compliance schema."
        )


# ==========================================
# FINDING #40 — LM STUDIO HEALTH / READINESS PROBE
# ==========================================
LM_STUDIO_PROBE_TIMEOUT_SECONDS = 3.0
# Short TTL cache so the frontend can poll readiness without hammering the
# local gateway between polls (one LLM call per ~15s worst case).
LM_STUDIO_HEALTH_CACHE_TTL_SECONDS = 15.0

_health_cache: Dict[str, Any] = {}
_health_cache_ts: float = 0.0


def reset_lm_studio_health_cache() -> None:
    """Clear the in-process TTL cache (exposed for tests and manual refresh)."""
    global _health_cache_ts
    _health_cache.clear()
    _health_cache_ts = 0.0


async def check_lm_studio_health(client_factory: Any = None) -> Dict[str, Any]:
    """
    Probe LM Studio's OpenAI-compatible ``GET /models`` endpoint.

    Unlike :func:`call_lm_studio` this probe **never raises**: it returns a
    structured readiness dict so callers (startup check, ``GET /api/health``,
    UI polls) can degrade gracefully when the local LLM is offline (Finding #40).

    Returns::

        {
            "online": bool,
            "latency_ms": float | None,
            "target_model": settings.LM_STUDIO_MODEL_FALLBACK,
            "model_loaded": bool,
            "loaded_models": [model ids currently served],
            "error": str | None,
            "checked_at": ISO-8601 UTC timestamp,
        }

    The result is cached for ``LM_STUDIO_HEALTH_CACHE_TTL_SECONDS``.
    ``client_factory`` is a dependency-injection seam used by unit tests; it
    defaults to :class:`httpx.AsyncClient`.
    """
    global _health_cache, _health_cache_ts

    now = time.monotonic()
    if _health_cache and (now - _health_cache_ts) < LM_STUDIO_HEALTH_CACHE_TTL_SECONDS:
        return dict(_health_cache)

    target_model = settings.LM_STUDIO_MODEL_FALLBACK
    result: Dict[str, Any] = {
        "online": False,
        "latency_ms": None,
        "target_model": target_model,
        "model_loaded": False,
        "loaded_models": [],
        "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    headers = {
        "Authorization": f"Bearer {settings.LM_STUDIO_API_KEY}",
        "Content-Type": "application/json",
    }
    probe_url = f"{settings.LM_STUDIO_URL.rstrip('/')}/models"
    started = time.perf_counter()
    factory = client_factory or httpx.AsyncClient

    try:
        async with factory(timeout=LM_STUDIO_PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get(probe_url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as http_err:
        result["error"] = (
            f"LM Studio returned HTTP {http_err.response.status_code} on {probe_url}."
        )
    except httpx.RequestError:
        result["error"] = "LM Studio is offline or unreachable."
    except Exception as err:  # malformed JSON / unexpected failures must not crash
        result["error"] = f"Health probe failed: {err}"

    if result["error"] is None:
        try:
            loaded_ids = [
                str(model.get("id", ""))
                for model in (payload.get("data", []) or [])
                if model.get("id")
            ]
            result.update({
                "online": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "loaded_models": loaded_ids,
                "model_loaded": target_model in loaded_ids,
            })
            if result["model_loaded"]:
                logger.info(
                    f"LM Studio health probe: online, model '{target_model}' loaded. "
                    f"loaded={loaded_ids}"
                )
            else:
                logger.warning(
                    f"LM Studio is online but model '{target_model}' is NOT loaded. "
                    f"loaded={loaded_ids or 'none'}"
                )
        except Exception as err:
            result["error"] = f"Malformed health payload: {err}"
    else:
        logger.warning(
            f"LM Studio health probe failed: {result['error']} "
            f"(gateway={settings.LM_STUDIO_URL}). Inference calls will fail with 503 "
            f"until the local server is started and a model is loaded."
        )

    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    _health_cache = dict(result)
    _health_cache_ts = time.monotonic()
    return dict(result)