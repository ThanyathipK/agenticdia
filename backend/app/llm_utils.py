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
    """
    # Priority 1: top-level .content string
    if hasattr(response, "content") and isinstance(response.content, str) and response.content.strip():
        return response.content
    # Priority 2: dict with "content"
    if isinstance(response, dict) and "content" in response:
        return str(response.get("content") or "")
    # Priority 3: provider-specific kwargs (reasoning models)
    if hasattr(response, "additional_kwargs"):
        kwargs = response.additional_kwargs or {}
        if kwargs.get("content"):
            return str(kwargs["content"])
        if kwargs.get("final_answer"):
            return str(kwargs["final_answer"])
    # Priority 4: response_metadata
    if hasattr(response, "response_metadata") and response.response_metadata.get("content"):
        return str(response.response_metadata["content"])
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
    if hasattr(parsed_output, "dict"):
        return parsed_output.dict()
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
    Invoke the LLM preferring structured output, falling back to raw JSON parsing.

    Attempt 1: runs ``prompt_template | llm.with_structured_output(schema)`` with
    ``variables`` and normalizes the result to a dict. When a ``validate`` callback
    is supplied, the result is only accepted if it returns True.

    Attempt 2 (if attempt 1 raised or failed validation): runs a raw invocation with
    the same ``variables`` but the full ``format_instructions``, strips markdown
    fences from the content, and parses it with ``json.loads``. The same
    ``validate`` callback is applied.

    Returns the parsed result as a plain dict. Raises ``RuntimeError`` when both
    attempts fail so the caller can apply its own heuristic fallback.
    """
    # Attempt 1: structured output
    try:
        logger.info(f"Attempting .with_structured_output() for {description}.")
        chain = prompt_template | llm.with_structured_output(schema)
        parsed_output = await chain.ainvoke(variables)
        result = normalize_output(parsed_output)
        if validate is None or validate(result):
            logger.info(f"Successfully obtained structured output for {description}.")
            return result
        logger.warning(f"Structured output for {description} failed validation. Falling back to raw parse.")
    except Exception as e:
        logger.warning(
            f"with_structured_output failed for {description}: {str(e)}. Falling back to raw parse."
        )

    # Attempt 2: raw invocation + JSON parsing
    try:
        raw_variables = {**variables, "format_instructions": format_instructions}
        raw_chain = prompt_template | llm
        raw_response = await raw_chain.ainvoke(raw_variables)
        clean_content = strip_markdown_fences(extract_llm_content(raw_response))
        result = json.loads(clean_content)
        if validate is None or validate(result):
            logger.info(f"Successfully parsed {description} from raw LLM output.")
            return result
    except Exception as e2:
        raise RuntimeError(f"All parsing attempts failed for {description}: {str(e2)}") from e2

    raise RuntimeError(f"All parsing attempts failed for {description}: result did not pass validation.")
