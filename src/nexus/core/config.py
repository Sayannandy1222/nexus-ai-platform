from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "nexus-ai-platform"

    environment: str = Field(
        default="development",
        alias="NEXUS_ENV",
    )

    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"

    # Redis / Valkey
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "nexus:v1"

    # Redis connection policy
    redis_max_connections: int = 50
    redis_connect_timeout_seconds: float = 2.0
    redis_socket_timeout_seconds: float = 1.0
    redis_health_check_interval_seconds: int = 30

    # RAG
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_top_k: int = 5

    # Semantic cache policy
    semantic_cache_ttl_seconds: int = 3600
    semantic_cache_max_bytes: int = 262_144

    # Document cache policy
    document_cache_ttl_seconds: int = 86_400

    # Agent memory policy
    session_ttl_seconds: int = 86_400
    session_max_messages: int = 100
    session_max_bytes: int = 1_000_000
    session_max_message_bytes: int = 10_000

    # Rate limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # LLM
    llm_provider: str = "mistral"
    mistral_api_key: str | None = None
    mistral_model: str = "mistral-small-latest"
    llm_request_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_retry_base_delay_seconds: float = 0.5
    llm_retry_max_delay_seconds: float = 5.0

    # Azure OpenAI - optional future provider
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None

    # Observability
    otel_enabled: bool = True
    otel_service_name: str = "nexus-api"
    otel_exporter_otlp_endpoint: str | None = None

    # BetterDB integration
    betterdb_enabled: bool = False
    betterdb_endpoint: str | None = None
    betterdb_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
