from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PRODUCTION_ENVIRONMENTS = {"prod", "production"}
INSECURE_JWT_SECRETS = {"", "change-me", "change-me-in-local-env"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    access_token_expire_minutes: int = 60 * 24 * 7
    allow_dev_auth_fallback: bool = True
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
    agent_runtime_default: str = "hermes"
    openclaw_base_url: str = "ws://127.0.0.1:18789"
    openclaw_agent_id: str = "main"
    openclaw_cli_path: str = "openclaw"
    openclaw_command_timeout_seconds: int = 600
    openclaw_mode: str = "gateway_cli"
    hermes_base_url: str = "http://localhost:8642"
    hermes_cli_path: str = "/home/zhuchangbiaozhu_xyl/.local/bin/hermes"
    hermes_home: str = "/home/zhuchangbiaozhu_xyl/.hermes"
    hermes_wsl_distribution: str = "Ubuntu"
    agent_run_idle_timeout_seconds: int = 30 * 60
    agent_run_overall_timeout_seconds: int = 2 * 60 * 60
    agent_run_ppt_export_timeout_seconds: int = 180
    agent_run_event_poll_interval_seconds: float = 1.0
    cleanup_enabled: bool = True
    cleanup_initial_delay_seconds: int = 60
    cleanup_interval_seconds: int = 6 * 60 * 60
    cleanup_runtime_file_max_age_days: int = 14
    cleanup_disconnected_run_max_age_days: int = 30

    @cached_property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @cached_property
    def is_production(self) -> bool:
        return self.environment.lower() in PRODUCTION_ENVIRONMENTS

    def validate_runtime_safety(self) -> None:
        if not self.is_production:
            return
        if self.allow_dev_auth_fallback:
            raise RuntimeError("ALLOW_DEV_AUTH_FALLBACK must be false in production.")
        if self.jwt_secret_key in INSECURE_JWT_SECRETS or len(self.jwt_secret_key) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be a strong secret in production.")
        if not self.cors_origins:
            raise RuntimeError("BACKEND_CORS_ORIGINS must include the production web origin.")


settings = Settings()
