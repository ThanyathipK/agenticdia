import logging

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.repository import ConversationMessageRepository
from app.schemas import ChatSessionRequest
from app.llm_client import call_lm_studio
from app.event_manager import event_manager

logger = logging.getLogger("app.routes.chat")

router = APIRouter()


@router.get("/api/health", status_code=status.HTTP_200_OK)
async def get_health_status():
    """Simple connection test endpoint for liveness validation checks."""
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "local_inference_gateway": settings.LM_STUDIO_URL,
        "macbook_context_window_budget": f"{settings.MAX_CONTEXT_TOKENS} tokens"
    }


@router.post("/api/chat", status_code=status.HTTP_200_OK)
async def post_chat_query(request: ChatSessionRequest):
    """
    Orchestrates requirements dialogue prompts with the local LLM.
    Acts as the entrypoint for LangGraph multi-agent context chains.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Conversation message list cannot be empty.")

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