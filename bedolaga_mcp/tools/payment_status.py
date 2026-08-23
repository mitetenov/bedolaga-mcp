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

#: Raw transaction types in the pinned Bedolaga Web API contract that represent
#: payment events. Fetching each type separately prevents newer reward/poll
#: transactions from hiding older payments behind the upstream page limit.
_UPSTREAM_PAYMENT_TYPES: tuple[str, ...] = (
    "deposit",
    "subscription_payment",
    "gift_payment",
    "refund",
    "failed_refund",
)

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
    raw_txs = await _fetch_payment_history(client, owner_id, limit)
    data = sanitize_payment_status(raw_txs, owner_id=owner_id, limit=limit)
    return make_success_envelope("bedolaga_payment_status_get", data)


async def _fetch_payment_history(
    client: BedolagaClient, user_id: int, limit: int
) -> dict[str, Any]:
    """Fetch and merge the latest records for every upstream payment type.

    The latest ``limit`` records from each disjoint type are sufficient to build
    the latest ``limit`` records across their union. Pages are still deduplicated
    by transaction id so a drifting upstream filter cannot duplicate output.
    """
    payloads = []
    for transaction_type in _UPSTREAM_PAYMENT_TYPES:
        payloads.append(
            await client.list_transactions(
                user_id,
                type=transaction_type,
                limit=limit,
                offset=0,
            )
        )
    return _merge_payment_pages(payloads)


def _merge_payment_pages(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge transaction pages and deduplicate records with the same id."""
    items: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    for payload in payloads:
        raw_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if item_id is not None and item_id in seen_ids:
                continue
            if item_id is not None:
                seen_ids.add(item_id)
            items.append(item)
    return {"items": items}
