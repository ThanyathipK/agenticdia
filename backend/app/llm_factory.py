"""Shared LangChain LLM client factory.

Centralises construction of the single ``ChatOpenAI`` instance used across the
multi-agent orchestrator (``app.agents``) and the semantic/intent/chat services
(``app.semantic_service``).

Historically ``semantic_service`` imported ``llm`` directly from ``app.agents``
(which constructed it at module scope), while ``app.agents`` had to import
``app.semantic_service`` only *inside* function bodies to avoid a circular import.

Having both modules consume ``llm`` / ``parser`` from this module instead breaks
that load-order dependency. ``app.semantic_service`` no longer imports from
``app.agents``, so ``app.agents`` can import its semantic helpers at module
scope without a deferred-import workaround.
"""
import logging

from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger("app.llm_factory")


# Safe context limit mapping designed for MacBook Air/Pro M4 16GB execution bounds
def build_llm() -> ChatOpenAI:
    """Construct the shared ChatOpenAI client from app.config settings.

    Exposed as a function so tests and callers can build/replace the client
    without recreating module state by hand.
    """
    return ChatOpenAI(
        base_url=settings.LM_STUDIO_URL,
        api_key=settings.LM_STUDIO_API_KEY,
        model=settings.LM_STUDIO_MODEL_FALLBACK,
        temperature=settings.TEMPERATURE,
        max_tokens=3000,  # Optimized for structured output
        seed=42,  # Deterministic sampling; declared as a first-class param (avoids model_kwargs warning)
    )


# Json Output Parser for strict structured JSON outputs
parser = JsonOutputParser()

# Single shared client for the whole process. Built eagerly at import time so the
# rest of the app can reference it without re-invoking the factory everywhere.
llm = build_llm()