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

    # Rate limiting (in-process sliding window; see app/rate_limit.py).
    # Finding #39: LLM-facing endpoints accept arbitrary input, so inbound
    # requests are throttled per client IP per scope.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_CHAT_LIMIT: int = 30
    RATE_LIMIT_CHAT_WINDOW: int = 60
    RATE_LIMIT_WORKFLOW_LIMIT: int = 20
    RATE_LIMIT_WORKFLOW_WINDOW: int = 60

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

    # Force configurations from .env file if available
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
logger.info(f"Loaded config for application: '{settings.APP_NAME}' with Context Limit: {settings.MAX_CONTEXT_TOKENS}")
