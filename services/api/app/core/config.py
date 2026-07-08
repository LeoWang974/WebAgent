from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    access_token_expire_minutes: int = 60 * 24 * 7
    api_prefix: str = "/api"
    app_name: str = "WebAgent API"
    backend_cors_origins: str = "http://localhost:3000"
    database_url: str = Field(
        default="postgresql+asyncpg://webagent:webagent_password@localhost:5432/webagent"
    )
    environment: str = "local"
    jwt_algorithm: str = "HS256"
    jwt_secret_key: str = "change-me"
    redis_url: str = "redis://localhost:6379/0"
    sensenova_api_key: str | None = None
    sensenova_base_url: str | None = None

    @cached_property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


settings = Settings()

