"""Real handler for the read-only ``bedolaga_gifts_get`` tool.

Resolves the caller by a system-pinned identity — exactly one of a positive
``telegram_id`` or the internal Bedolaga ``user_id`` (used for email-only
cabinet tickets) — then resolves the internal user id on the server side,
fetches the owner's gift purchase accounting events via ``GET /transactions``,
and returns the sanitized gift purchases list.

The identity never comes from the model: both or neither argument raises
:class:`~bedolaga_mcp.errors.InvalidInputError`. The handler is read-only and
makes no write requests.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..sanitize import sanitize_gifts
from .identity import resolve_owner

__all__ = ["bedolaga_gifts_get"]


async def bedolaga_gifts_get(
    client: BedolagaClient,
    *,
    telegram_id: int | None = None,
    user_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return the current user's gift purchase accounting transactions.

    ``client`` is injected by the registry. Exactly one of ``telegram_id``
    (positive Telegram ID) or ``user_id`` (internal Bedolaga id) is required;
    both or neither raises ``invalid_input``. ``limit`` is bounded by the
    registered schema (1..50, default 20). Flow: resolve owner →
    list_transactions (type=gift_purchase) → sanitize_gifts → success envelope.
    """
    raw_user, owner_id = await resolve_owner(
        client, telegram_id=telegram_id, user_id=user_id
    )
    raw_transactions = await client.list_transactions(
        owner_id, type="gift_purchase", limit=limit, offset=0
    )
    data = sanitize_gifts(raw_transactions, owner_id=owner_id, limit=limit)
    return make_success_envelope("bedolaga_gifts_get", data)
