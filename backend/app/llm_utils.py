import json
import logging
from typing import Any, Callable, Dict, Optional, Type

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel

logger = logging.getLogger("app.llm_utils")


def extract_llm_content(response: Any) -> str:
    """
    Robustly extracts the text payload from a LangChain LLM response.

    Handles AIMessage-like objects (.content), plain dictionaries holding a
    "content" key, and providers that nest the answer under additional_kwargs
    (e.g. reasoning models exposing "content" / "final_answer").

    Reasoning models served by LM Studio (e.g. Qwen3.x) frequently place the
    actual answer inside ``reasoning_content`` while leaving ``content`` EMPTY
    (verified live: even with ``enable_thinking=false`` the server still emits
    the JSON answer in reasoning_content). When content is blank, the reasoning
    text is the only payload available, so it is returned for JSON parsing —
    returning an empty string here used to make every structured generation
    fail and fall through to the error path.
    """
    # Priority 1: top-level .content string
    if hasattr(response, "content") and isinstance(response.content, str) and response.content.strip():
        return response.content
    # Priority 1b: reasoning models answering in reasoning_content with empty content
    if hasattr(response, "additional_kwargs"):
        kwargs = response.additional_kwargs or {}
        reasoning = kwargs.get("reasoning_content") or kwargs.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
    # Priority 2: dict with "content" (non-blank) or a reasoning fallback
    if isinstance(response, dict):
        if "content" in response and str(response.get("content") or "").strip():
            return str(response.get("content") or "")
        reasoning = response.get("reasoning_content") or response.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
    # Priority 3: provider-specific kwargs (reasoning models)
    if hasattr(response, "additional_kwargs"):
        kwargs = response.additional_kwargs or {}
        if kwargs.get("content"):
            return str(kwargs["content"])
        if kwargs.get("final_answer"):
            return str(kwargs["final_answer"])
    # Priority 4: response_metadata
    if hasattr(response, "response_metadata") and response.response_metadata:
        metadata = response.response_metadata
        if metadata.get("content"):
            return str(metadata["content"])
        reasoning = metadata.get("reasoning_content") or metadata.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
    return str(response)


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences (```json / ```) surrounding a JSON payload."""
    clean = text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    return clean.strip()


def normalize_output(parsed_output: Any) -> Dict[str, Any]:
    """Convert a Pydantic model or mapping into a plain dict."""
    if hasattr(parsed_output, "model_dump"):
        return parsed_output.model_dump()
    if isinstance(parsed_output, dict):
        return parsed_output
    return dict(parsed_output)


async def invoke_llm_structured(
    llm,
    prompt_template: PromptTemplate,
    schema: Type[BaseModel],
    variables: Dict[str, Any],
    *,
    description: str = "LLM structured output",
    format_instructions: str,
    validate: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> Dict[str, Any]:
    """
    Invoke the LLM and return the parsed result as a plain dict.

    Attempt 1 (primary): ONE raw invocation carrying the full
    ``format_instructions``; markdown fences are stripped and the content is
    parsed as JSON. Raw parsing is the primary path because the deployed
    LM Studio / Qwen build does not honor json-schema enforcement —
    ``with_structured_output`` fails on EVERY call there (the answer lands in
    ``reasoning_content``), which silently DOUBLED each generation's latency
    and token cost before the fallback ever ran. ``extract_llm_content``
    recovers the answer from ``reasoning_content`` when ``content`` is empty.

    Attempt 2 (fallback): ``prompt_template | llm.with_structured_output(schema)``
    for providers whose structured-output mode actually works.

    The same optional ``validate`` callback gates both attempts.

    Returns the parsed result as a plain dict. Raises ``RuntimeError`` when both
    attempts fail so the caller can apply its own heuristic fallback.
    """
    # Attempt 1: single raw invocation + JSON parsing
    raw_failure = "unknown"
    try:
        raw_variables = {**variables, "format_instructions": format_instructions}
        raw_chain = prompt_template | llm
        raw_response = await raw_chain.ainvoke(raw_variables)
        clean_content = strip_markdown_fences(extract_llm_content(raw_response))
        result = json.loads(clean_content)
        if validate is None or validate(result):
            logger.info(f"Successfully parsed {description} from raw LLM output.")
            return result
        raw_failure = f"raw output failed validation for {description}"
        logger.warning(f"{raw_failure}. Falling back to structured output.")
    except Exception as e:
        raw_failure = str(e)
        logger.warning(f"Raw parse failed for {description}: {e}. Falling back to structured output.")

    # Attempt 2: provider structured output (fallback)
    try:
        logger.info(f"Attempting .with_structured_output() for {description}.")
        chain = prompt_template | llm.with_structured_output(schema)
        parsed_output = await chain.ainvoke(variables)
        result = normalize_output(parsed_output)
        if validate is None or validate(result):
            logger.info(f"Successfully obtained structured output for {description}.")
            return result
        raise RuntimeError(f"structured output failed validation for {description}")
    except Exception as e2:
        raise RuntimeError(
            f"All parsing attempts failed for {description} (raw attempt: {raw_failure}): {str(e2)}"
        ) from e2
