# File purpose: Verifies test health behavior and its regression contracts.
# Main declarations: _set_check handles set check; test_health_reports_ready_dependencies verifies
# health reports ready dependencies; test_health_reports_postgresql_failure verifies health
# reports postgresql failure; test_health_reports_redis_failure verifies health reports redis
# failure; test_redis_check_handles_invalid_configuration verifies redis check handles invalid
# configuration.

import json

import pytest

from app.api.routes import health


def _set_check(monkeypatch, name: str, result: bool) -> None:
    async def check() -> bool:
        return result

    monkeypatch.setattr(health, name, check)


@pytest.mark.asyncio
async def test_health_reports_ready_dependencies(monkeypatch):
    _set_check(monkeypatch, "_check_postgresql", True)
    _set_check(monkeypatch, "_check_redis", True)

    response = await health.health_check()

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "ok",
        "checks": {"postgresql": "ok", "redis": "ok"},
    }


@pytest.mark.asyncio
async def test_health_reports_postgresql_failure(monkeypatch):
    _set_check(monkeypatch, "_check_postgresql", False)
    _set_check(monkeypatch, "_check_redis", True)

    response = await health.health_check()

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "unavailable",
        "checks": {"postgresql": "unavailable", "redis": "ok"},
    }


@pytest.mark.asyncio
async def test_health_reports_redis_failure(monkeypatch):
    _set_check(monkeypatch, "_check_postgresql", True)
    _set_check(monkeypatch, "_check_redis", False)

    response = await health.health_check()

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "unavailable",
        "checks": {"postgresql": "ok", "redis": "unavailable"},
    }


@pytest.mark.asyncio
async def test_redis_check_handles_invalid_configuration(monkeypatch):
    def invalid_redis_url(*args, **kwargs):
        del args, kwargs
        raise ValueError("invalid Redis URL")

    monkeypatch.setattr(health.Redis, "from_url", invalid_redis_url)

    assert await health._check_redis() is False
