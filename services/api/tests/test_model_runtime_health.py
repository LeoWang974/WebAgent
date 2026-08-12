from types import SimpleNamespace

import pytest

from app.api.routes.settings import check_runtime_model
from app.models import ModelConfig


class FailingHermesAdapter:
    async def health_check(self):
        return {
            "exitCode": 7,
            "ok": False,
            "stderr": "gateway refused connection",
            "stdout": "",
        }


class RaisingHermesAdapter:
    async def health_check(self):
        raise RuntimeError("gateway timed out")


def make_model():
    return ModelConfig(
        base_url="https://token.sensenova.cn/v1",
        is_available=True,
        is_default=False,
        name="sensenova-6.7-flash-lite",
        provider="openai_compatible",
        user_id="user_1",
    )


@pytest.fixture(autouse=True)
def stub_runtime_config(monkeypatch):
    async def fake_build_for_user(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.routes.settings.model_runtime_config_builder.build_for_user",
        fake_build_for_user,
    )


@pytest.mark.asyncio
async def test_runtime_model_reports_hermes_health_failure(monkeypatch):
    def fake_create_hermes_adapter(*args, **kwargs):
        return FailingHermesAdapter()

    monkeypatch.setattr(
        "app.services.agent_runs.create_hermes_adapter",
        fake_create_hermes_adapter,
    )

    result = await check_runtime_model(SimpleNamespace(), SimpleNamespace(), make_model())

    assert result["adapterKey"] == "hermes"
    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["message"] == "Runtime health check failed."
    assert result["health"] == {
        "exitCode": 7,
        "ok": False,
        "stderr": "gateway refused connection",
        "stdout": "",
    }


@pytest.mark.asyncio
async def test_runtime_model_reports_hermes_health_exception(monkeypatch):
    def fake_create_hermes_adapter(*args, **kwargs):
        return RaisingHermesAdapter()

    monkeypatch.setattr(
        "app.services.agent_runs.create_hermes_adapter",
        fake_create_hermes_adapter,
    )

    result = await check_runtime_model(SimpleNamespace(), SimpleNamespace(), make_model())

    assert result["adapterKey"] == "hermes"
    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["message"] == "gateway timed out"
