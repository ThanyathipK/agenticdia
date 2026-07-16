import os
import logging
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
        return url

    # Local LLM / LM Studio Orchestration Settings
    LM_STUDIO_URL: str = "http://localhost:1234/v1"
    LM_STUDIO_API_KEY: str = "lm-studio"
    LM_STUDIO_MODEL_FALLBACK: str = "qwen2.5-7b-instruct"

    # Context & Memory Safety Constraints (optimised for MacBook Air M4 with 16GB RAM)
    MAX_CONTEXT_TOKENS: int = 8192
    TEMPERATURE: float = 0.0

    # Application details
    APP_NAME: str = "Enterprise Requirements Architecture Core"
    DEBUG: bool = False

    # Force configurations from .env file if available
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
logger.info(f"Loaded config for application: '{settings.APP_NAME}' with Context Limit: {settings.MAX_CONTEXT_TOKENS}")
