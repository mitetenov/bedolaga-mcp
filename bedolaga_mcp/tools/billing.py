"""Real handler for the read-only ``bedolaga_billing_get`` tool.

Resolves the caller by a system-pinned identity — exactly one of a positive
``telegram_id`` or the internal Bedolaga ``user_id`` (used for email-only
cabinet tickets) — then resolves the internal user id on the server side,
fetches a bounded transaction history (see :func:`_fetch_billing_history` for
the documented strategy) and returns the sanitized billing payload: balance,
recent transactions capped at ``limit``, the latest-completed deposit /
subscription-purchase summaries, ``purchased_after_latest_deposit`` and the
bot-side subscription records.

The identity never comes from the model: both or neither argument raises
:class:`~bedolaga_mcp.errors.InvalidInputError`. The handler is read-only and
makes no write requests. All error mapping happens in the registry;
:func:`require_internal_id` raises
:class:`~bedolaga_mcp.errors.IdentityUnavailableError` when the resolved user
has no usable internal id, which becomes an ``identity_unavailable`` envelope.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..errors import InvalidInputError
from ..sanitize import sanitize_billing
from . import require_internal_id

#: Largest single-page limit the upstream ``/transactions`` endpoint accepts.
_UPSTREAM_PAGE_LIMIT: int = 200

__all__ = ["bedolaga_billing_get"]


async def bedolaga_billing_get(
    client: BedolagaClient,
    *,
    telegram_id: int | None = None,
    user_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return balance, recent financial events and bot-side purchase records.

    ``client`` is injected by the registry. Exactly one of ``telegram_id``
    (positive Telegram ID) or ``user_id`` (internal Bedolaga id) is required;
    both or neither raises ``invalid_input``. ``limit`` is already bounded to
    1..50 by the pydantic schema derived from the registered handler. The flow
    is: one user resolution → internal user id → a bounded transaction fetch →
    the sanitizer → the success envelope.
    """
    if (telegram_id is None) == (user_id is None):
        raise InvalidInputError("Provide exactly one of telegram_id or user_id")
    raw_user = (
        await client.get_user_by_telegram_id(telegram_id)
        if telegram_id is not None
        else await client.get_user_by_id(user_id)
    )
    owner_id = require_internal_id(raw_user)
    history = await _fetch_billing_history(client, owner_id)
    data = sanitize_billing(raw_user, history, limit)
    return make_success_envelope("bedolaga_billing_get", data)


async def _fetch_billing_history(
    client: BedolagaClient, user_id: int
) -> dict[str, Any]:
    """Fetch a bounded, deduplicated transaction set for the billing summaries.

    Strategy (documented): one general page at the upstream maximum (200) gives
    the recent transactions shown to the model, plus type-filtered pages for
    ``deposit`` and ``subscription_payment`` so the latest completed deposit and
    purchase still count in the summaries even when they are older than 200
    interleaved events. The three pages are merged and deduplicated by
    transaction id; the sanitizer still caps the returned ``transactions`` list
    at ``limit`` and never exposes the full volume.
    """
    general = await client.list_transactions(
        user_id, limit=_UPSTREAM_PAGE_LIMIT, offset=0
    )
    deposits = await client.list_transactions(
        user_id, type="deposit", limit=_UPSTREAM_PAGE_LIMIT, offset=0
    )
    purchases = await client.list_transactions(
        user_id, type="subscription_payment", limit=_UPSTREAM_PAGE_LIMIT, offset=0
    )
    return _merge_transactions([general, deposits, purchases])


def _merge_transactions(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge transaction payloads, deduplicating by transaction id.

    The overlapping pages (a deposit page overlaps the general page, for
    example) must not produce duplicate rows in the returned list, so items are
    keyed by their transaction ``id``; items without an id are kept as-is.
    """
    by_id: dict[Any, dict[str, Any]] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        items = payload.get("items")
        if not isinstance(items, list):
            continue
        for tx in items:
            if not isinstance(tx, dict):
                continue
            key = tx.get("id")
            if key is None:
                key = ("__no_id__", len(by_id))
            by_id.setdefault(key, tx)
    return {"items": list(by_id.values())}
