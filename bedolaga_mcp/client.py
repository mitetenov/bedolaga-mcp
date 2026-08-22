"""Async HTTP client for the Bedolaga Bot Web API.

This is the only module that talks to Bedolaga. All calls are read-only GETs
against the routes pinned in the upstream contract (commit 49b05d5), share one
owned :class:`httpx.AsyncClient` and the timeout from config, and map every
failure onto the domain errors from :mod:`bedolaga_mcp.errors`. The API key is
sent only in the ``X-API-Key`` header and never appears in URLs, exceptions,
logs or returned payloads.
"""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from .config import Config
from .errors import (
    InvalidInputError,
    InvalidUpstreamResponseError,
    RateLimitedError,
    UnauthorizedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    UserNotFoundError,
    bounded_body,
)

_TIMEOUT_CLASSES = (httpx.TimeoutException,)
_NETWORK_CLASSES = (httpx.NetworkError,)


class BedolagaClient:
    """Reusable async client bound to one :class:`~bedolaga_mcp.config.Config`.

    Constructs and owns a single :class:`httpx.AsyncClient`. Use as an async
    context manager or close it explicitly via :meth:`aclose` when the MCP
    process shuts down.
    """

    def __init__(self, config: Config) -> None:
        self._base_url = config.api_url
        self._api_key = config.api_key
        self._timeout = httpx.Timeout(config.timeout_seconds)
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def __aenter__(self) -> "BedolagaClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned httpx client and its connection pool."""
        await self._client.aclose()

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any]:
        """GET /users/by-telegram-id/{telegram_id} → UserResponse."""
        self._require_id("telegram_id", telegram_id)
        return await self._get(f"/users/by-telegram-id/{telegram_id}")

    async def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        """GET /users/{user_id} → UserResponse (internal Bedolaga user id)."""
        self._require_id("user_id", user_id)
        return await self._get(f"/users/{user_id}")

    async def list_transactions(
        self,
        user_id: int,
        type: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /transactions with user_id (and optional type/limit/offset)."""
        self._require_id("user_id", user_id)
        params: dict[str, Any] = {"user_id": user_id}
        if type is not None:
            if not isinstance(type, str) or not type.strip():
                raise InvalidInputError("type must be a non-empty string")
            params["type"] = type
        if limit is not None:
            self._require_limit("limit", limit)
            params["limit"] = limit
        self._require_offset("offset", offset)
        params["offset"] = offset
        return await self._get("/transactions", params=params)

    async def get_referrer_detail(
        self,
        user_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /partners/referrers/{user_id} → PartnerReferrerDetail."""
        self._require_id("user_id", user_id)
        params: dict[str, Any] = {}
        if limit is not None:
            self._require_limit("limit", limit)
            params["limit"] = limit
        self._require_offset("offset", offset)
        params["offset"] = offset
        return await self._get(f"/partners/referrers/{user_id}", params=params)

    async def _get(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send one read-only GET and map every failure onto domain errors.

        The full URL is composed in this single place from the config-normalized
        base URL; query parameters go through httpx so nothing is ever
        string-concatenated by callers. The API key travels only in the
        ``X-API-Key`` header.
        """
        url = f"{self._base_url}{path}"
        headers = {"X-API-Key": self._api_key}

        try:
            response = await self._client.get(url, params=params, headers=headers)
        except _TIMEOUT_CLASSES as exc:
            raise UpstreamTimeoutError("Bedolaga API request timed out") from exc
        except _NETWORK_CLASSES as exc:
            raise UpstreamTimeoutError("Bedolaga API is unreachable") from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                "Bedolaga API request failed"
            ) from exc

        if response.status_code == 404:
            raise UserNotFoundError("User not found")
        if response.status_code in (401, 403):
            raise UnauthorizedError("Invalid or missing Bedolaga API credentials")
        if response.status_code == 429:
            raise RateLimitedError("Bedolaga API rate limit reached")
        if response.status_code == 422:
            raise InvalidInputError("Bedolaga API rejected the request parameters")
        if response.status_code >= 500:
            raise UpstreamUnavailableError("Bedolaga API is unavailable")
        if response.status_code != 200:
            raise UpstreamUnavailableError(
                f"Unexpected Bedolaga API status {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidUpstreamResponseError(
                "Bedolaga API returned an invalid response",
                detail=bounded_body(response.text),
            ) from exc

        if not isinstance(payload, dict):
            raise InvalidUpstreamResponseError(
                "Bedolaga API returned an unexpected response shape"
            )
        return payload

    @staticmethod
    def _require_id(name: str, value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise InvalidInputError(f"{name} must be a positive integer")

    @staticmethod
    def _require_limit(name: str, value: Any) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= 200
        ):
            raise InvalidInputError(f"{name} must be an integer between 1 and 200")

    @staticmethod
    def _require_offset(name: str, value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InvalidInputError(f"{name} must be a non-negative integer")


__all__ = ["BedolagaClient"]
