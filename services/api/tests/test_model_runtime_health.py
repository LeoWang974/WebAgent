from types import SimpleNamespace

import pytest

from app.api.routes.settings import check_runtime_model
from app.models import ModelConfig


class FailingOpenClawAdapter:
    async def health_check(self):
        return {
            "exitCode": 7,
            "ok": False,
            "stderr": "gateway refused connection",
            "stdout": "",
        }


class RaisingOpenClawAdapter:
    async def health_check(self):
        raise RuntimeError("gateway timed out")


def make_model():
    return ModelConfig(
        base_url="ws://127.0.0.1:18789",
        is_available=True,
        is_default=False,
        name="OpenClaw Agent",
        provider="openai_compatible",
        user_id="user_1",
    )


@pytest.mark.asyncio
async def test_runtime_model_reports_openclaw_health_failure(monkeypatch):
    async def fake_resolve_adapter_for_model(_db, _current_user, _model_id):
        return "openclaw", FailingOpenClawAdapter()

    monkeypatch.setattr(
        "app.services.agent_runs.resolve_adapter_for_model",
        fake_resolve_adapter_for_model,
    )

    result = await check_runtime_model(SimpleNamespace(), SimpleNamespace(), make_model())

    assert result["adapterKey"] == "openclaw"
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
async def test_runtime_model_reports_openclaw_health_exception(monkeypatch):
    async def fake_resolve_adapter_for_model(_db, _current_user, _model_id):
        return "openclaw", RaisingOpenClawAdapter()

    monkeypatch.setattr(
        "app.services.agent_runs.resolve_adapter_for_model",
        fake_resolve_adapter_for_model,
    )

    result = await check_runtime_model(SimpleNamespace(), SimpleNamespace(), make_model())

    assert result["adapterKey"] == "openclaw"
    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["message"] == "gateway timed out"
