# File purpose: Verifies test config behavior and its regression contracts.
# Main declarations: test_production_requires_agent_run_queue verifies production requires agent
# run queue.

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings


def test_production_requires_agent_run_queue() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        model_config_encryption_key=Fernet.generate_key().decode("ascii"),
        allow_dev_auth_fallback=False,
        jwt_secret_key="a-secure-production-secret-that-is-long-enough",
        backend_cors_origins="https://webagent.example.com",
        agent_run_queue_enabled=False,
    )

    with pytest.raises(RuntimeError, match="AGENT_RUN_QUEUE_ENABLED"):
        settings.validate_runtime_safety()
