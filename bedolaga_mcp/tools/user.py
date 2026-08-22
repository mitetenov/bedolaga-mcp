"""Real handler for the read-only ``bedolaga_user_get`` tool.

Resolves the caller by Telegram ID only — no internal user id, username, email,
transaction id or referral code is ever accepted — then sanitizes the raw user
payload through the allowlist sanitizer and wraps it in the unified success
envelope. All error mapping happens in the registry: this handler only calls
the client, the sanitizer and :func:`contracts.make_success_envelope`, so the
tool layer never composes an error message by hand.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..sanitize import sanitize_user

__all__ = ["bedolaga_user_get"]


async def bedolaga_user_get(
    client: BedolagaClient, telegram_id: int
) -> dict[str, Any]:
    """Return the current user's account and balance by Telegram ID.

    ``client`` is injected by the registry. The handler is read-only: it makes
    exactly one ``GET /users/by-telegram-id/{telegram_id}`` and returns the
    sanitized account facts, never forbidden fields.
    """
    raw_user = await client.get_user_by_telegram_id(telegram_id)
    data = sanitize_user(raw_user)
    return make_success_envelope("bedolaga_user_get", data)
