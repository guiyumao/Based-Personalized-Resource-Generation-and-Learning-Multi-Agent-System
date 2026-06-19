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

    qwen_api_base: str = os.getenv("QWEN_API_BASE", "")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen-plus")
    deepseek_api_base: str = os.getenv("DEEPSEEK_API_BASE", "")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    chroma_persist_directory: str = os.getenv("CHROMA_PERSIST_DIRECTORY", "./.chroma")
    llm_request_timeout_seconds: int = _get_int("LLM_REQUEST_TIMEOUT_SECONDS", 30)
    resource_rag_top_k: int = _get_int("RESOURCE_RAG_TOP_K", 2)
    resource_courseware_variant_count: int = _get_int("RESOURCE_COURSEWARE_VARIANT_COUNT", 1)
    exercise_context_max_chars: int = _get_int("EXERCISE_CONTEXT_MAX_CHARS", 900)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so all services share one loaded instance."""

    return Settings()
