"""Real handler for the read-only ``bedolaga_subscription_get`` tool.

Resolves the caller by a system-pinned identity — exactly one of a positive
``telegram_id`` or the internal Bedolaga ``user_id`` (used for email-only
cabinet tickets) — then resolves the internal user id on the server side,
fetches the owner's subscription records via ``GET /subscriptions``, merges
lifecycle dates with user tariff facts, and returns the sanitized bot-side
subscription payload.

The identity never comes from the model: both or neither argument raises
:class:`~bedolaga_mcp.errors.InvalidInputError`. The handler is read-only and
makes no write requests.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..sanitize import sanitize_subscriptions
from .identity import resolve_owner

__all__ = ["bedolaga_subscription_get"]


async def bedolaga_subscription_get(
    client: BedolagaClient,
    *,
    telegram_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Return the current user's bot-side subscription records and lifecycle dates.

    ``client`` is injected by the registry. Exactly one of ``telegram_id``
    (positive Telegram ID) or ``user_id`` (internal Bedolaga id) is required;
    both or neither raises ``invalid_input``. The flow is: one user resolution →
    internal owner id → list_subscriptions → merge with user tariff facts →
    the sanitizer → the success envelope.
    """
    raw_user, owner_id = await resolve_owner(
        client, telegram_id=telegram_id, user_id=user_id
    )
    raw_subscriptions = await client.list_subscriptions(
        owner_id, limit=200, offset=0
    )
    data = sanitize_subscriptions(raw_user, raw_subscriptions, owner_id)
    return make_success_envelope("bedolaga_subscription_get", data)
