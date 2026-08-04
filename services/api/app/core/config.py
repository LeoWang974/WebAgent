import binascii
from functools import cached_property

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PRODUCTION_ENVIRONMENTS = {"prod", "production"}
INSECURE_JWT_SECRETS = {"", "change-me", "change-me-in-local-env"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "services/api/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    model_config_encryption_key: str | None = None
    model_config_encryption_previous_keys: str = ""
    sensenova_api_key: str | None = None
    sensenova_base_url: str | None = None
    sensenova_default_model: str = "sensenova-6.7-flash-lite"
    agent_runtime_default: str = "hermes"
    openclaw_base_url: str = "ws://127.0.0.1:18789"
    openclaw_agent_id: str = "main"
    openclaw_cli_path: str = "openclaw"
    openclaw_command_timeout_seconds: int = 600
    openclaw_mode: str = "gateway_cli"
    hermes_base_url: str = "http://localhost:8642"
    hermes_cli_path: str = "hermes"
    hermes_home: str = "~/.hermes"
    hermes_skills_dir: str | None = None
    hermes_wsl_distribution: str = "Ubuntu"
    openclaw_skills_dir: str | None = None
    agent_run_idle_timeout_seconds: int = 30 * 60
    agent_run_overall_timeout_seconds: int = 2 * 60 * 60
    agent_run_ppt_export_timeout_seconds: int = 180
    agent_run_event_poll_interval_seconds: float = 1.0
    upload_max_size_bytes: int = 25 * 1024 * 1024
    agent_run_queue_enabled: bool = False
    agent_run_queue_name: str = "agent-runs"
    short_chat_queue_name: str = "short-chat"
    agent_run_workspace_root: str = "runtime/agent-runs"
    agent_runtime_user_root: str = "runtime/users"
    agent_adapter_limit_scope: str = "per_user"
    agent_adapter_default_concurrency: int = 1
    hermes_adapter_concurrency: int = 1
    openclaw_adapter_concurrency: int = 1
    agent_adapter_lock_poll_seconds: float = 2.0
    agent_adapter_lock_status_interval_seconds: int = 30
    agent_adapter_lock_ttl_seconds: int = 120
    agent_adapter_lock_wait_timeout_seconds: int = 60 * 60
    artifact_storage_enabled: bool = True
    artifact_storage_root: str = r"D:\WebAgentArtifacts"
    cleanup_enabled: bool = True
    cleanup_initial_delay_seconds: int = 60
    cleanup_interval_seconds: int = 6 * 60 * 60
    cleanup_runtime_file_max_age_days: int = 14
    cleanup_disconnected_run_max_age_days: int = 30
    skills_update_enabled: bool = True
    skills_update_repo_url: str = "https://github.com/OpenSenseNova/SenseNova-Skills.git"
    skills_update_branch: str | None = None
    skills_update_cache_dir: str | None = None
    skills_update_source_subdir: str = "skills"
    skills_update_timezone: str = "Asia/Shanghai"
    skills_update_weekday: int = 4
    skills_update_hour: int = 17
    skills_update_minute: int = 0
    skills_update_run_on_startup: bool = False

    @cached_property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @cached_property
    def is_production(self) -> bool:
        return self.environment.lower() in PRODUCTION_ENVIRONMENTS

    def validate_runtime_safety(self) -> None:
        if not self.model_config_encryption_key:
            raise RuntimeError("MODEL_CONFIG_ENCRYPTION_KEY is required.")
        try:
            Fernet(self.model_config_encryption_key.strip().encode("ascii"))
        except (binascii.Error, TypeError, ValueError) as error:
            raise RuntimeError(
                "MODEL_CONFIG_ENCRYPTION_KEY must be a valid Fernet key."
            ) from error
        if not self.is_production:
            return
        if self.allow_dev_auth_fallback:
            raise RuntimeError("ALLOW_DEV_AUTH_FALLBACK must be false in production.")
        if self.jwt_secret_key in INSECURE_JWT_SECRETS or len(self.jwt_secret_key) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be a strong secret in production.")
        if not self.cors_origins:
            raise RuntimeError("BACKEND_CORS_ORIGINS must include the production web origin.")


settings = Settings()
