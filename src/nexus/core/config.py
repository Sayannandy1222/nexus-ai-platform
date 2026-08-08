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

    app_name: str = "nexus-ai-platform"
    environment: str = Field(default="development", alias="NEXUS_ENV")
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "nexus:v1"

    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_top_k: int = 5

    cache_ttl_seconds: int = 604800
    session_ttl_seconds: int = 86400

    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    llm_provider: str = "azure_openai"

    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None

    otel_enabled: bool = True
    otel_service_name: str = "nexus-api"
    otel_exporter_otlp_endpoint: str | None = None

    betterdb_enabled: bool = False
    betterdb_endpoint: str | None = None
    betterdb_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
