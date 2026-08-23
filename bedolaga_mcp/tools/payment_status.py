"""Real handler for the read-only ``bedolaga_payment_status_get`` tool.

Resolves the caller by a system-pinned identity — exactly one of a positive
``telegram_id`` or the internal Bedolaga ``user_id`` (used for email-only
cabinet tickets) — then resolves the internal user id on the server side,
fetches recent accounting transactions via ``GET /transactions``, filters by
financial payment categories, normalizes the accounting status (completed /
not_completed / unknown), and returns the sanitized payments list.

The identity never comes from the model: both or neither argument raises
:class:`~bedolaga_mcp.errors.InvalidInputError`. The handler is read-only and
makes no write requests.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..sanitize import sanitize_payment_status
from .identity import resolve_owner

#: Upper bound of transactions fetched from upstream to build the payment list.
_UPSTREAM_TRANSACTIONS_LIMIT: int = 200

__all__ = ["bedolaga_payment_status_get"]


async def bedolaga_payment_status_get(
    client: BedolagaClient,
    *,
    telegram_id: int | None = None,
    user_id: int | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Return the current user's accounting payment events and status.

    ``client`` is injected by the registry. Exactly one of ``telegram_id``
    (positive Telegram ID) or ``user_id`` (internal Bedolaga id) is required;
    both or neither raises ``invalid_input``. ``limit`` is bounded to 1..20
    (default 5). Flow: resolve owner → list_transactions → filter payment
    categories → sanitize accounting status → success envelope.
    """
    raw_user, owner_id = await resolve_owner(
        client, telegram_id=telegram_id, user_id=user_id
    )
    raw_txs = await client.list_transactions(
        owner_id, limit=_UPSTREAM_TRANSACTIONS_LIMIT, offset=0
    )
    data = sanitize_payment_status(raw_txs, owner_id=owner_id, limit=limit)
    return make_success_envelope("bedolaga_payment_status_get", data)
