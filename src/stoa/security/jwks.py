"""Bounded, issuer-isolated asynchronous JWKS key retrieval."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import time
from typing import Callable, Protocol

import httpx
from jose.backends import RSAKey as _RSAKey
from jose.backends.base import Key

from stoa.security.errors import SecurityDecisionError, SecurityErrorCode


class JwksTransport(Protocol):
    async def fetch(self, issuer: str) -> Mapping[str, object]: ...


def _string_keyed_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


class HttpxJwksTransport:
    def __init__(self, *, connect_timeout: float, read_timeout: float) -> None:
        self._timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )

    async def fetch(self, issuer: str) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{issuer.rstrip('/')}/.well-known/jwks.json")
            response.raise_for_status()
            payload = _string_keyed_object(response.json())
        if payload is None:
            raise ValueError("JWKS response is not an object")
        return payload


@dataclass(frozen=True, slots=True)
class _CachedKey:
    key: Key
    fetched_at: float


class JwksKeyProvider:
    """Cache keys by issuer and kid; refresh each issuer with one single-flight task."""

    def __init__(
        self,
        transport: JwksTransport,
        *,
        ttl_seconds: float,
        max_stale_seconds: float,
        unknown_kid_cooldown_seconds: float = 30.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or max_stale_seconds < ttl_seconds:
            raise ValueError("invalid JWKS cache bounds")
        if unknown_kid_cooldown_seconds < 0:
            raise ValueError("invalid JWKS unknown-kid cooldown")
        self._transport = transport
        self._ttl = ttl_seconds
        self._max_stale = max_stale_seconds
        self._unknown_kid_cooldown = unknown_kid_cooldown_seconds
        self._monotonic = monotonic
        self._keys: dict[str, dict[str, _CachedKey]] = {}
        self._wasted_refresh_at: dict[str, float] = {}
        self._refresh_tasks: dict[str, asyncio.Task[None]] = {}
        self._task_lock = asyncio.Lock()

    async def get_key(self, issuer: str, kid: str) -> Key:
        if not issuer or not kid:
            raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN)
        now = self._monotonic()
        cached = self._keys.get(issuer, {}).get(kid)
        if cached is not None and now - cached.fetched_at <= self._ttl:
            return cached.key

        if cached is None and not self._forced_refresh_allowed(issuer, now):
            raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN)

        try:
            await self._refresh(issuer)
        except Exception as exc:
            if cached is not None and now - cached.fetched_at <= self._max_stale:
                return cached.key
            raise SecurityDecisionError(
                SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE,
                internal_detail=type(exc).__name__,
            ) from exc

        refreshed = self._keys.get(issuer, {}).get(kid)
        if refreshed is None:
            self._wasted_refresh_at[issuer] = self._monotonic()
            raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN)
        return refreshed.key

    def _forced_refresh_allowed(self, issuer: str, now: float) -> bool:
        """Charge an unresolvable kid one fetch per cooldown, not one per request.

        Only a refresh that failed to produce the requested kid starts the
        cooldown, so a real rotation is still discovered on its first request.
        """
        if not self._keys.get(issuer):
            return True
        wasted_at = self._wasted_refresh_at.get(issuer)
        if wasted_at is None:
            return True
        return now - wasted_at >= self._unknown_kid_cooldown

    async def _refresh(self, issuer: str) -> None:
        async with self._task_lock:
            task = self._refresh_tasks.get(issuer)
            if task is None or task.done():
                task = asyncio.create_task(self._fetch_and_store(issuer))
                self._refresh_tasks[issuer] = task
        try:
            await task
        finally:
            async with self._task_lock:
                if self._refresh_tasks.get(issuer) is task and task.done():
                    self._refresh_tasks.pop(issuer, None)

    async def _fetch_and_store(self, issuer: str) -> None:
        payload = await self._transport.fetch(issuer)
        raw_keys = payload.get("keys")
        if not isinstance(raw_keys, list):
            raise ValueError("JWKS keys are missing")
        fetched_at = self._monotonic()
        parsed: dict[str, _CachedKey] = {}
        for raw_key in raw_keys:
            key_data = _string_keyed_object(raw_key)
            if key_data is None:
                continue
            kid = key_data.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            if key_data.get("kty") != "RSA" or key_data.get("alg") not in {None, "RS256"}:
                continue
            key_type = _RSAKey
            if key_type is None:
                raise ValueError("RS256 key support is unavailable")
            parsed[kid] = _CachedKey(key_type(key_data, algorithm="RS256"), fetched_at)
        if not parsed:
            raise ValueError("JWKS contains no usable RS256 keys")
        self._keys[issuer] = parsed
