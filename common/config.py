"""Shared configuration objects used across services."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv_file() -> None:
    """Load a local `.env` file into process environment if present."""

    env_path = Path(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # Deployment-provided environment variables must take precedence over
        # developer defaults stored in the local .env file.
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv_file()


def _get_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable with a sensible fallback."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    """Read an integer environment variable with fallback on parse errors."""

    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    """Read a floating-point environment variable with fallback."""

    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_required(name: str) -> str:
    """Read a required environment variable."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _get_csv(name: str, default: str = "") -> tuple[str, ...]:
    """Read a comma-separated environment variable."""

    value = os.getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    project_name: str = os.getenv("PROJECT_NAME", "personalized-learning-system")
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = _get_bool("DEBUG", True)

    database_url: str = os.getenv("DATABASE_URL", "sqlite+pysqlite:///./learning_system.db")
    redis_url: str = os.getenv("REDIS_URL", "")
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "")
    elasticsearch_url: str = os.getenv("ELASTICSEARCH_URL", "")
    user_service_url: str = os.getenv("USER_SERVICE_URL", "")
    agent_service_url: str = os.getenv("AGENT_SERVICE_URL", "")
    resource_service_url: str = os.getenv("RESOURCE_SERVICE_URL", "")
    evaluation_service_url: str = os.getenv("EVALUATION_SERVICE_URL", "")
    teacher_service_url: str = os.getenv("TEACHER_SERVICE_URL", "")
    system_service_url: str = os.getenv("SYSTEM_SERVICE_URL", "")
    cors_allow_origins: tuple[str, ...] = _get_csv("CORS_ALLOW_ORIGINS")

    neo4j_uri: str = os.getenv("NEO4J_URI", "")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "")
    neo4j_enabled: bool = _get_bool("NEO4J_ENABLED", bool(os.getenv("NEO4J_URI")))

    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "")
    minio_secure: bool = _get_bool("MINIO_SECURE", False)
    minio_bucket: str = os.getenv("MINIO_BUCKET", "learning-assets")

    jwt_secret_key: str = _get_required("JWT_SECRET_KEY")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = _get_int("JWT_EXPIRE_MINUTES", 120)
    password_salt: str = os.getenv("PASSWORD_SALT", "")

    default_admin_username: str = os.getenv("DEFAULT_ADMIN_USERNAME", "")
    default_admin_password: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "")
    default_admin_email: str = os.getenv("DEFAULT_ADMIN_EMAIL", "")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    qwen_api_key: str = os.getenv("QWEN_API_KEY", "")
    qwen_api_base: str = os.getenv("QWEN_API_BASE", "")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen-plus")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_api_base: str = os.getenv("DEEPSEEK_API_BASE", "")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    llm_light_model: str = os.getenv("LLM_LIGHT_MODEL", "")
    chroma_mode: str = os.getenv("CHROMA_MODE", "persistent").strip().lower()
    chroma_persist_directory: str = os.getenv("CHROMA_PERSIST_DIRECTORY", "./knowledge_base/index")
    chroma_host: str = os.getenv("CHROMA_HOST", "chroma")
    chroma_port: int = _get_int("CHROMA_PORT", 8000)
    chroma_ssl: bool = _get_bool("CHROMA_SSL", False)
    chroma_collection_name: str = os.getenv("CHROMA_COLLECTION_NAME", "education_resources")
    chroma_collection_version: str = os.getenv("CHROMA_COLLECTION_VERSION", "v1")
    #: Chroma 0.5.x has no authentication, so the service refuses to connect to a
    #: non-loopback/non-private host unless this is explicitly enabled.
    chroma_allow_remote_host: bool = _get_bool("CHROMA_ALLOW_REMOTE_HOST", False)
    knowledge_base_version: str = os.getenv("KNOWLEDGE_BASE_VERSION", "v1")
    corpus_version: str = os.getenv("RAG_CORPUS_VERSION", "v1")
    embedding_model_version: str = os.getenv("EMBEDDING_MODEL_VERSION", "chroma-default-v1")
    retrieval_config_version: str = os.getenv("RAG_RETRIEVAL_CONFIG_VERSION", "v2")
    ai_performance_log_path: str = os.getenv(
        "AI_PERFORMANCE_LOG_PATH", "./logs/ai-performance.jsonl"
    )
    rag_chunk_size: int = _get_int("RAG_CHUNK_SIZE", 800)
    rag_chunk_overlap: int = _get_int("RAG_CHUNK_OVERLAP", 120)
    rag_chunker_version: str = os.getenv("RAG_CHUNKER_VERSION", "markdown-heading-v2")
    rag_retrieval_top_k: int = _get_int("RAG_RETRIEVAL_TOP_K", 5)
    rag_final_top_k: int = _get_int("RAG_FINAL_TOP_K", 4)
    rag_cache_ttl_seconds: int = _get_int("RAG_CACHE_TTL_SECONDS", 900)
    rag_cache_max_entries: int = _get_int("RAG_CACHE_MAX_ENTRIES", 512)
    rag_lexical_fast_path: bool = _get_bool("RAG_LEXICAL_FAST_PATH", True)
    rag_lexical_min_score: float = _get_float("RAG_LEXICAL_MIN_SCORE", 0.35)
    rag_index_use_llm_tags: bool = _get_bool("RAG_INDEX_USE_LLM_TAGS", False)
    rag_score_ambiguity_threshold: float = _get_float("RAG_SCORE_AMBIGUITY_THRESHOLD", 0.03)
    max_total_retries: int = _get_int("MAX_TOTAL_RETRIES", 2)
    qa_deadline_seconds: int = _get_int("QA_DEADLINE_SECONDS", 60)
    chat_deadline_seconds: int = _get_int("CHAT_DEADLINE_SECONDS", 60)
    exercise_deadline_seconds: int = _get_int("EXERCISE_DEADLINE_SECONDS", 20)
    learning_path_deadline_seconds: int = _get_int("LEARNING_PATH_DEADLINE_SECONDS", 30)
    courseware_deadline_seconds: int = _get_int("COURSEWARE_DEADLINE_SECONDS", 60)
    report_deadline_seconds: int = _get_int("REPORT_DEADLINE_SECONDS", 30)
    llm_request_timeout_seconds: int = _get_int("LLM_REQUEST_TIMEOUT_SECONDS", 45)
    llm_prewarm_enabled: bool = _get_bool("LLM_PREWARM_ENABLED", True)
    resource_rag_top_k: int = _get_int("RESOURCE_RAG_TOP_K", 5)
    resource_courseware_variant_count: int = _get_int("RESOURCE_COURSEWARE_VARIANT_COUNT", 1)
    exercise_context_max_chars: int = _get_int("EXERCISE_CONTEXT_MAX_CHARS", 900)

    # Knowledge-graph visualization. The visualization payload is derived from
    # Neo4j/SQL/courseware content; the LLM may only *enrich* it in the
    # background, never block the request (DEF-012).
    graph_cache_ttl_seconds: int = _get_int("GRAPH_CACHE_TTL_SECONDS", 900)
    graph_cache_max_entries: int = _get_int("GRAPH_CACHE_MAX_ENTRIES", 256)
    graph_llm_enrich_enabled: bool = _get_bool("GRAPH_LLM_ENRICH_ENABLED", True)
    graph_llm_enrich_timeout_seconds: int = _get_int("GRAPH_LLM_ENRICH_TIMEOUT_SECONDS", 20)
    graph_enrich_max_workers: int = _get_int("GRAPH_ENRICH_MAX_WORKERS", 4)
    # Minimum spacing between background enrichment jobs, plus a startup grace
    # period. Running LLM work during a request intermittently stalled the caller
    # by ~2.2s, so enrichment is deferred and serialized instead.
    graph_enrich_min_interval_seconds: float = _get_float("GRAPH_ENRICH_MIN_INTERVAL_SECONDS", 2.0)
    graph_enrich_startup_delay_seconds: float = _get_float("GRAPH_ENRICH_STARTUP_DELAY_SECONDS", 20.0)
    # A configured-but-unreachable Neo4j used to add ~4s to *every* graph request
    # (driver default connection timeout). Bound it and trip a breaker after
    # repeated failures so an outage degrades instead of stalling (DEF-012).
    neo4j_connection_timeout_seconds: float = _get_float("NEO4J_CONNECTION_TIMEOUT_SECONDS", 1.0)
    neo4j_query_timeout_seconds: float = _get_float("NEO4J_QUERY_TIMEOUT_SECONDS", 2.0)
    neo4j_failure_threshold: int = _get_int("NEO4J_FAILURE_THRESHOLD", 2)
    neo4j_cooldown_seconds: int = _get_int("NEO4J_COOLDOWN_SECONDS", 60)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so all services share one loaded instance."""

    return Settings()
