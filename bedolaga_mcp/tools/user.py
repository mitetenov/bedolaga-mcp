"""Real handler for the read-only ``bedolaga_user_get`` tool.

Resolves the caller by a system-pinned identity — exactly one of a positive
``telegram_id`` or the internal Bedolaga ``user_id`` (used for email-only
cabinet tickets) — then sanitizes the raw user payload through the allowlist
sanitizer and wraps it in the unified success envelope. The identity never
comes from the model: both or neither argument raises
:class:`~bedolaga_mcp.errors.InvalidInputError`, and no username, email,
transaction id or referral code is ever accepted. All error mapping happens in
the registry: this handler only calls the client, the sanitizer and
:func:`contracts.make_success_envelope`, so the tool layer never composes an
error message by hand.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..errors import InvalidInputError
from ..sanitize import sanitize_user

__all__ = ["bedolaga_user_get"]


async def bedolaga_user_get(
    client: BedolagaClient,
    *,
    telegram_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Return the current user's account and balance by pinned identity.

    ``client`` is injected by the registry. Exactly one of ``telegram_id``
    (positive Telegram ID) or ``user_id`` (internal Bedolaga id) is required;
    both or neither raises ``invalid_input``. The handler is read-only: it
    makes exactly one resolution call and returns the sanitized account facts,
    never forbidden fields.
    """
    if (telegram_id is None) == (user_id is None):
        raise InvalidInputError("Provide exactly one of telegram_id or user_id")
    raw_user = (
        await client.get_user_by_telegram_id(telegram_id)
        if telegram_id is not None
        else await client.get_user_by_id(user_id)
    )
    data = sanitize_user(raw_user)
    return make_success_envelope("bedolaga_user_get", data)
