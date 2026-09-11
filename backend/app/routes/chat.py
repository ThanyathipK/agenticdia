import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.repositories import ConversationMessageRepository
from app.schemas import ChatSessionRequest, ChatResponse, HealthResponse
from app.semantic_memory import build_memory_block, extract_and_remember, recall
from app.llm_client import (
    call_lm_studio,
    check_lm_studio_health,
    LMStudioGatewayError,
    LMStudioOutputParsingError,
    LMStudioUnavailableError,
)
from app.event_manager import event_manager
from app.rate_limit import rate_limit_dependency
from app.input_validation import validate_messages_budget

logger = logging.getLogger("app.routes.chat")

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def get_health_status() -> HealthResponse:
    """
    Readiness probe combining app liveness with a real LM Studio check (Finding #40).

    Runs a short ``GET /models`` round-trip against the configured local gateway
    (TTL-cached server-side) so callers can detect an offline LLM immediately and
    degrade gracefully. The app itself still answers ``200 online`` even when the
    LLM is down — connectivity is reported through the ``lm_studio_online`` /
    ``lm_studio_error`` fields instead of an error status.

    Returns:
        HealthResponse: Application identity, configured inference gateway and
        context-window budget, plus live LM Studio readiness information.
    """
    lm_health = await check_lm_studio_health()
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "local_inference_gateway": settings.LM_STUDIO_URL,
        "macbook_context_window_budget": f"{settings.MAX_CONTEXT_TOKENS} tokens",
        "lm_studio_online": lm_health["online"],
        "lm_studio_model": lm_health["target_model"],
        "lm_studio_model_loaded": lm_health["model_loaded"],
        "lm_studio_loaded_models": lm_health["loaded_models"],
        "lm_studio_latency_ms": lm_health["latency_ms"],
        "lm_studio_error": lm_health["error"],
        "lm_studio_last_checked": lm_health["checked_at"],
    }


@router.post("/api/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def post_chat_query(
    request: ChatSessionRequest,
    _rate_limit: None = Depends(
        rate_limit_dependency(
            "chat", settings.RATE_LIMIT_CHAT_LIMIT, settings.RATE_LIMIT_CHAT_WINDOW
        )
    ),
) -> ChatResponse:
    """
    Orchestrates requirements dialogue prompts with the local LLM.

    Acts as the entrypoint for LangGraph multi-agent context chains. Persists
    each user/assistant turn (when a ``project_id`` is provided) and notifies
    SSE subscribers of new assistant replies.

    Args:
        request: Conversation timeline plus optional project context.
        _rate_limit: Injected rate limiter (Finding #39) — rejects excess
            requests with HTTP 429 before any LLM work happens.

    Returns:
        ChatResponse: The assistant's generated reply text.

    Raises:
        HTTPException: 400 if the message list is empty; 413 if the combined
            message history exceeds ``MAX_CONTEXT_TOKENS``.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Conversation message list cannot be empty.")

    # Finding #39: enforce MAX_CONTEXT_TOKENS on incoming payload before any
    # token budget is consumed by the LLM gateway.
    validate_messages_budget(request.messages)

    # --- Semantic memory recall (fail-open) --------------------------------
    # Before the LLM call, retrieve the most relevant distilled memories for
    # this project (scored on the CURRENT user message) and inject them as a
    # hard-capped block into the system prompt. Any failure degrades to the
    # pre-memory behaviour — chat never breaks because memory is down.
    memory_block = ""
    if request.project_id and settings.MEMORY_ENABLED:
        current_message = request.messages[-1].content
        try:
            memories = await recall(str(request.project_id), current_message)
            memory_block = build_memory_block(memories)
        except Exception as mem_err:  # belt & braces: recall is already fail-open
            logger.warning("Memory recall skipped (%s).", mem_err)

    system_instruction = (
        "You are an expert enterprise business analyst specializing in core banking requirement designs. "
        "Adhere to Krungsri Nimble standards, ensure high compliance, security OTP mechanics, and double-entry general ledgers. "
        f"Strictly keep your replies inside a total contextual window budget of {settings.MAX_CONTEXT_TOKENS} tokens."
    )
    if memory_block:
        system_instruction = (
            f"{system_instruction}\n\n{memory_block}\n"
            "Use the remembered project context when it is relevant; never contradict a "
            "recorded user decision without saying so."
        )

    formatted_messages = [{"role": "system", "content": system_instruction}]
    for msg in request.messages:
        formatted_messages.append({"role": msg.role, "content": msg.content})
        if request.project_id:
            await ConversationMessageRepository.save_message(
                project_id=str(request.project_id),
                role=msg.role,
                message=msg.content,
                workflow_state="chat",
                intent="GENERAL_CHAT"
            )

    logger.info("Initiating conversational analyst run.")
    try:
        response = await call_lm_studio(formatted_messages)
    except LMStudioOutputParsingError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))
    except LMStudioUnavailableError as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err))
    except LMStudioGatewayError as err:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err))
    reply_text = response.get("text", "")

    if request.project_id and reply_text:
        await ConversationMessageRepository.save_message(
            project_id=str(request.project_id),
            role="assistant",
            message=reply_text,
            workflow_state="chat",
            intent="GENERAL_CHAT"
        )
        # Semantic memory write path (fail-open): distil durable facts from
        # this finished turn so FUTURE conversations understand the project
        # better. Runs after the reply is persisted; failures are logged and
        # swallowed — the user's reply is already delivered either way.
        last_user_message = next(
            (m.content for m in reversed(request.messages) if m.role == "user"),
            "",
        )
        if last_user_message and settings.MEMORY_FACT_EXTRACTION_ENABLED:
            await extract_and_remember(
                project_id=str(request.project_id),
                user_message=last_user_message,
                assistant_reply=reply_text,
            )
        # Notify SSE subscribers so other connected clients refresh their conversation view.
        await event_manager.publish(str(request.project_id), "chat_reply", {
            "project_id": str(request.project_id),
            "role": "assistant",
        })

    return {"message": reply_text}