import json
import logging
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