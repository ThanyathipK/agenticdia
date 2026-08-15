import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.repository import ConversationMessageRepository
from app.schemas import ChatSessionRequest, ChatResponse, HealthResponse
from app.llm_client import call_lm_studio, check_lm_studio_health
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

    system_instruction = (
        "You are an expert enterprise business analyst specializing in core banking requirement designs. "
        "Adhere to Krungsri Nimble standards, ensure high compliance, security OTP mechanics, and double-entry general ledgers. "
        f"Strictly keep your replies inside a total contextual window budget of {settings.MAX_CONTEXT_TOKENS} tokens."
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
    response = await call_lm_studio(formatted_messages)
    reply_text = response.get("text", "")

    if request.project_id and reply_text:
        await ConversationMessageRepository.save_message(
            project_id=str(request.project_id),
            role="assistant",
            message=reply_text,
            workflow_state="chat",
            intent="GENERAL_CHAT"
        )
        # Notify SSE subscribers so other connected clients refresh their conversation view.
        await event_manager.publish(str(request.project_id), "chat_reply", {
            "project_id": str(request.project_id),
            "role": "assistant",
        })

    return {"message": reply_text}