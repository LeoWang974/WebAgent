import asyncio
import secrets
from collections.abc import Awaitable, Callable
from time import monotonic

import redis.asyncio as redis

from app.core.config import settings

WaitCallback = Callable[[float], Awaitable[None]]


class AdapterCapacityTimeout(Exception):
    pass


class AdapterCapacityLease:
    def __init__(
        self,
        client: redis.Redis,
        key: str,
        token: str,
        ttl_seconds: int,
    ) -> None:
        self.client = client
        self.key = key
        self.token = token
        self.ttl_seconds = ttl_seconds
        self._refresh_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "AdapterCapacityLease":
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        await self.release()
        await self.client.aclose()

    async def _refresh_loop(self) -> None:
        refresh_interval = max(1, self.ttl_seconds // 3)
        while True:
            await asyncio.sleep(refresh_interval)
            current_token = await self.client.get(self.key)
            if current_token != self.token:
                return
            await self.client.expire(self.key, self.ttl_seconds)

    async def release(self) -> None:
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        end
        return 0
        """
        await self.client.eval(script, 1, self.key, self.token)


class NoopAdapterCapacityLease:
    async def __aenter__(self) -> "NoopAdapterCapacityLease":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def adapter_concurrency_limit(adapter_key: str | None) -> int:
    if adapter_key == "hermes":
        return settings.hermes_adapter_concurrency
    if adapter_key == "openclaw":
        return settings.openclaw_adapter_concurrency
    return settings.agent_adapter_default_concurrency


def adapter_lock_scope(scope: str | None) -> str:
    configured_scope = settings.agent_adapter_limit_scope.strip().lower()
    if configured_scope in {"global", "adapter"}:
        return "global"
    return scope or "global"


async def acquire_adapter_capacity(
    adapter_key: str | None,
    run_id: str,
    *,
    scope: str | None = None,
    on_wait: WaitCallback | None = None,
) -> AdapterCapacityLease | NoopAdapterCapacityLease:
    limit = adapter_concurrency_limit(adapter_key)
    if limit <= 0:
        return NoopAdapterCapacityLease()

    normalized_adapter_key = adapter_key or "default"
    normalized_scope = adapter_lock_scope(scope)
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    token = f"{run_id}:{secrets.token_urlsafe(16)}"
    started_at = monotonic()
    last_wait_status_at = 0.0

    try:
        while True:
            for slot in range(limit):
                key = f"webagent:adapter-lock:{normalized_adapter_key}:{normalized_scope}:{slot}"
                acquired = await client.set(
                    key,
                    token,
                    ex=settings.agent_adapter_lock_ttl_seconds,
                    nx=True,
                )
                if acquired:
                    return AdapterCapacityLease(
                        client,
                        key,
                        token,
                        settings.agent_adapter_lock_ttl_seconds,
                    )

            elapsed = monotonic() - started_at
            if elapsed >= settings.agent_adapter_lock_wait_timeout_seconds:
                raise AdapterCapacityTimeout(
                    f"Timed out waiting for {normalized_adapter_key} adapter capacity "
                    f"after {int(elapsed)} seconds."
                )
            if (
                on_wait is not None
                and elapsed - last_wait_status_at
                >= settings.agent_adapter_lock_status_interval_seconds
            ):
                last_wait_status_at = elapsed
                await on_wait(elapsed)
            await asyncio.sleep(settings.agent_adapter_lock_poll_seconds)
    except Exception:
        await client.aclose()
        raise
