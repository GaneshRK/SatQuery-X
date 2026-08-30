"""Application configuration via environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    satquery_env: str = "development"
    satquery_secret_key: str = "dev-secret-change-me"
    satquery_jwt_secret: str = "dev-jwt-secret-change-me"

    database_url: str = "postgresql+asyncpg://satquery:satquery@localhost:5432/satquery"
    database_url_sync: str = "postgresql://satquery:satquery@localhost:5432/satquery"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "satquery"
    s3_region: str = "us-east-1"

    planner_llm_provider: str = "rules"
    openai_api_key: str = ""
    planner_model: str = "gpt-4o-mini"

    model_device: str = "cpu"
    rs_vqa_model: str = "Salesforce/blip-vqa-base"
    rs_caption_model: str = "Salesforce/blip-image-captioning-base"

    max_upload_size_mb: int = 100

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
