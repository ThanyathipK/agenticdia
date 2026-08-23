import os
import logging
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

# Set up standard logging configuration for enterprise-grade audits
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("app.config")

class Settings(BaseSettings):
    """
    Enterprise Banking System Configuration.
    Loads variables dynamically from .env or ambient environment variables.
    """
    # Database Settings
    DATABASE_URL: str = "sqlite+aiosqlite:///app.db"

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if not url:
            return "sqlite+aiosqlite:///app.db"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # Add SSL mode for Supabase cloud connections
        if "supabase.com" in url and "ssl=" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}ssl=require"
        return url

    # Local LLM / LM Studio Orchestration Settings
    LM_STUDIO_URL: str = "http://localhost:1234/v1"
    LM_STUDIO_API_KEY: str = "lm-studio"
    # Default model id used for inference. Override via LM_STUDIO_MODEL_FALLBACK in
    # backend/.env to match whatever model is loaded in LM Studio (no longer a
    # hard-coded reference — see Finding #40). backend/.env.example ships qwen3.5.
    LM_STUDIO_MODEL_FALLBACK: str = "qwen3.5-9b-instruct"

    # Context & Memory Safety Constraints (optimised for MacBook Air M4 with 16GB RAM)
    MAX_CONTEXT_TOKENS: int = 8192
    TEMPERATURE: float = 0.0

    # Document upload & extraction (see app/routes/documents.py, app/document_processor.py)
    # MAX_UPLOAD_MB is the ONLY size gate applied at save time — it guards against
    # disk abuse. It is deliberately NOT a token check: the FULL converted markdown
    # is always persisted regardless of size. Token limits apply solely to the
    # LLM-feeding path (the explicit "process this document" action).
    MAX_UPLOAD_MB: int = 25
    # Fraction of MAX_CONTEXT_TOKENS reserved for a document chunk so the system
    # prompt + gatherer instructions + tool schema + output slack still fit when
    # the chunk is joined to the prompt (Option 2 math — never set the chunk near
    # the full context window).
    DOCUMENT_BUDGET_FRACTION: float = 0.6
    # Target token size of a single document chunk (~10% overlap keeps headings
    # and context from being clipped at chunk boundaries).
    DOCUMENT_CHUNK_SIZE: int = 2500
    DOCUMENT_CHUNK_OVERLAP: int = 250
    # Hard ceiling on how many sequential chunked-lambda runs a single document
    # extraction may produce. Beyond this the extraction is refused (413) with a
    # clear message instead of silently degrading into a truncation.
    MAX_DOCUMENT_CHUNKS: int = 30

    # Rate limiting (per-client sliding window; see app/rate_limit.py).
    # Finding #39: LLM-facing endpoints accept arbitrary input, so inbound
    # requests are throttled per client IP per scope.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_CHAT_LIMIT: int = 30
    RATE_LIMIT_CHAT_WINDOW: int = 60
    RATE_LIMIT_WORKFLOW_LIMIT: int = 60
    RATE_LIMIT_WORKFLOW_WINDOW: int = 60

    # Store backing the limiter. Only "in-process" is implemented today; the
    # startup guard (verify_single_worker_guarantee) then REQUIRES a single
    # uvicorn worker and refuses to boot otherwise, so 429 protection can never
    # silently disappear under a multi-process deployment. Set this to a
    # distributed store's name only once such a backend exists.
    RATE_LIMIT_STORE: str = "in-process"
    # Explicit opt-out: keep the in-process store across N workers (each worker
    # then gets its own independent budget). This is a *weaker* posture; the
    # app still logs a loud warning at startup when workers > 1.
    RATE_LIMIT_ALLOW_MULTI_PROCESS_IN_PROCESS: bool = False
    # Proxy-aware keying: when the immediate socket peer is one of
    # TRUSTED_PROXY_IPS, the real client IP is read from the rightmost
    # X-Forwarded-For / Forwarded entry. Headers are ignored unless the peer is
    # trusted, so a client can never widen its own bucket by spoofing them.
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXY_IPS: str = ""

    # SSE pub/sub reliability (see app/event_manager.py).
    # The event bus is in-process (process-local subscriber queues + replay
    # buffer) and, like the rate limiter, is safe only for a single uvicorn
    # worker. The startup guard (verify_single_worker_guarantee) refuses to boot
    # when multiple workers are detected, so live updates can never silently
    # split across workers. A bounded per-project ring buffer
    # (SSE_HISTORY_BUFFER_SIZE) lets a reconnecting client replay events it
    # missed while disconnected (SSE Last-Event-ID); history is process-local so
    # a full restart loses it (forward progress resumes on the next publish).
    SSE_HISTORY_BUFFER_SIZE: int = 1000
    # Explicit opt-out: run N workers with the in-process SSE bus (broken event
    # delivery by construction). The app logs a loud warning at startup instead
    # of refusing to boot. Not recommended.
    SSE_ALLOW_MULTI_PROCESS_IN_PROCESS: bool = False

    # Application details
    APP_NAME: str = "Enterprise Requirements Architecture Core"
    DEBUG: bool = False

    # CORS security: explicit allowed origins (comma-separated in .env).
    # Never use "*" with allow_credentials=True — browsers reject this combination.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse the comma-separated CORS_ORIGINS string into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def trusted_proxy_ip_list(self) -> List[str]:
        """Parse the comma-separated TRUSTED_PROXY_IPS string into a list."""
        return [ip.strip() for ip in self.TRUSTED_PROXY_IPS.split(",") if ip.strip()]

    # Force configurations from .env file if available
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
logger.info(f"Loaded config for application: '{settings.APP_NAME}' with Context Limit: {settings.MAX_CONTEXT_TOKENS}")
