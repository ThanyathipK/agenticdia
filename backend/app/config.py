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
    # Qwen3.x models are REASONING models: they first emit a long `reasoning_content`
    # chain-of-thought and only then the real answer. With a bounded max_tokens the
    # model can exhaust the whole budget thinking and return an EMPTY `content`
    # (finish_reason="length"), so every structured-JSON parser fails and PRD /
    # audit generation surfaces as "Connection error" / "cannot generate PRD".
    # When enabled, every request sets chat_template_kwargs={"enable_thinking": false}
    # so the model writes its answer directly to `content` (fast + JSON-parseable).
    LM_STUDIO_DISABLE_THINKING: bool = True

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
    # Target token size of a single document chunk (overlap keeps headings and
    # context from being clipped at chunk boundaries).
    #
    # Sizing math (MAX_CONTEXT_TOKENS=8192, gatherer max_tokens=3000, ~700
    # prompt/system/format tokens): chunk 3500 + overlap 250 = 3750 input tokens
    # leaves 3750 tokens of headroom for the prompt and the extracted JSON, so a
    # single pass stays comfortably inside the window. Bigger chunks => fewer
    # gatherer passes => faster extraction for otherwise-equal document content.
    DOCUMENT_CHUNK_SIZE: int = 3500
    DOCUMENT_CHUNK_OVERLAP: int = 250
    # Bounded parallelism across chunked gatherer passes. 1 = fully sequential
    # (safe default for a single-slot local LM Studio model on a 16 GB laptop).
    # Raise to 2-4 when the inference gateway can serve concurrent requests
    # (LM Studio multi-slot, or an OpenAI-compatible cloud endpoint) to cut the
    # wall-clock time of many-chunk documents almost linearly. Results keep their
    # document order regardless of this value.
    DOCUMENT_EXTRACTION_CONCURRENCY: int = 1
    # Hard ceiling on how many chunked gatherer passes a single document
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
    # Semantic memory (see app/semantic_memory.py).
    # Distilled project facts + conversation embeddings retrieved at prompt
    # build time so agents "remember" prior decisions across sessions. The
    # whole pipeline is FAIL-OPEN: any LM Studio/DB failure degrades to the
    # pre-memory behaviour instead of breaking the chat turn.
    MEMORY_ENABLED: bool = True
    # Master switch for the LLM fact-extraction pass (recall stays on).
    MEMORY_FACT_EXTRACTION_ENABLED: bool = True
    # Embedding model served by LM Studio (nomic-embed-text = 768 dims, fast on M4).
    LM_STUDIO_EMBEDDING_MODEL: str = "text-embedding-nomic-embed-text-v1.5"
    # Embedding request timeout (embeddings must never block a chat turn long).
    MEMORY_EMBEDDING_TIMEOUT_SECONDS: float = 10.0
    # How many memories are injected into a prompt at most.
    MEMORY_TOP_K: int = 6
    # Hard token ceiling for the "Relevant project memory" prompt block,
    # mirroring the MAX_CONTEXT_TOKENS budget discipline (Finding #39).
    MEMORY_CONTEXT_MAX_TOKENS: int = 800
    # Candidate scan window: only the N most recent memories per project are
    # scored in-process (keeps the Python cosine pass O(400) worst case).
    MEMORY_CANDIDATE_LIMIT: int = 400
    # Relevance blend: score = MEMORY_RELEVANCE_WEIGHT * cosine
    #                 + (1 - MEMORY_RELEVANCE_WEIGHT) * recency_factor,
    # where recency_factor = 0.5 ** (age_days / MEMORY_RECENCY_HALF_LIFE_DAYS).
    MEMORY_RELEVANCE_WEIGHT: float = 0.7
    MEMORY_RECENCY_HALF_LIFE_DAYS: float = 30.0
    # New facts with cosine similarity >= this against an existing memory are
    # considered duplicates and skipped (keeps memory from bloating).
    MEMORY_DEDUPE_SIMILARITY: float = 0.92
    # Cap on facts extracted from a single chat turn (token-budget hygiene).
    MEMORY_MAX_FACTS_PER_TURN: int = 8

    # SSE pub/sub reliability (see app/event_manager.py).

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
