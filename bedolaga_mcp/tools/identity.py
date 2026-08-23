"""Shared helpers for resolving pinned identities across Bedolaga MCP tools.

All Bedolaga tools accept a pinned identity: exactly one of ``telegram_id``
(positive Telegram user ID) or ``user_id`` (internal positive Bedolaga account
ID). Identity is always pinned by the caller system, never by the model.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..errors import IdentityUnavailableError, InvalidInputError


def require_internal_id(raw_user: Any) -> int:
    """Return the owner's internal user id or raise IdentityUnavailableError.

    When the resolved user has no usable internal id (missing, non-integer,
    bool, or <= 0), no downstream call is made and IdentityUnavailableError
    is raised.
    """
    user_id = raw_user.get("id") if isinstance(raw_user, dict) else None
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise IdentityUnavailableError(
            "User identity cannot be resolved to a Bedolaga account"
        )
    return user_id


def _validate_identity_args(telegram_id: int | None, user_id: int | None) -> None:
    if (telegram_id is None) == (user_id is None):
        raise InvalidInputError("Provide exactly one of telegram_id or user_id")
    if telegram_id is not None:
        if isinstance(telegram_id, bool) or not isinstance(telegram_id, int) or telegram_id <= 0:
            raise InvalidInputError("telegram_id must be a positive integer")
    if user_id is not None:
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise InvalidInputError("user_id must be a positive integer")


async def resolve_user(
    client: BedolagaClient,
    *,
    telegram_id: int | None,
    user_id: int | None,
) -> dict[str, Any]:
    """Resolve a raw user payload by pinned telegram_id or internal user_id."""
    _validate_identity_args(telegram_id, user_id)
    if telegram_id is not None:
        return await client.get_user_by_telegram_id(telegram_id)
    assert user_id is not None
    return await client.get_user_by_id(user_id)


async def resolve_owner(
    client: BedolagaClient,
    *,
    telegram_id: int | None,
    user_id: int | None,
) -> tuple[dict[str, Any], int]:
    """Resolve user record and extract the internal owner user id."""
    raw_user = await resolve_user(client, telegram_id=telegram_id, user_id=user_id)
    owner_id = require_internal_id(raw_user)
    return raw_user, owner_id


__all__ = [
    "require_internal_id",
    "resolve_owner",
    "resolve_user",
]
