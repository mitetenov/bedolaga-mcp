"""Real handler for the read-only ``bedolaga_promocode_check`` tool.

Resolves the caller by a system-pinned identity — exactly one of a positive
``telegram_id`` or the internal Bedolaga ``user_id`` (used for email-only
cabinet tickets) — then searches the global promo code registry via
``GET /promo-codes`` in bounded pages (up to 5 pages / 1000 items), masks the
code plaintext, and returns global validity without revealing creator or
third-party usage data.

The identity never comes from the model: both or neither argument raises
:class:`~bedolaga_mcp.errors.InvalidInputError`. The handler is read-only and
makes no write requests.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..errors import InvalidInputError
from ..sanitize import sanitize_promocode
from .identity import resolve_owner

_PAGE_LIMIT: int = 200
_MAX_PAGES: int = 5

__all__ = ["bedolaga_promocode_check"]


async def bedolaga_promocode_check(
    client: BedolagaClient,
    *,
    telegram_id: int | None = None,
    user_id: int | None = None,
    code: str,
) -> dict[str, Any]:
    """Check global promo code definition and bonus rules.

    ``client`` is injected by the registry. Exactly one of ``telegram_id``
    (positive Telegram ID) or ``user_id`` (internal Bedolaga id) is required;
    both or neither raises ``invalid_input``. ``code`` is required and must be
    a non-empty string. Flow: resolve owner → search /promo-codes in bounded
    pages → exact match → sanitize & mask → success envelope.
    """
    if not isinstance(code, str) or not code.strip():
        raise InvalidInputError("code must be a non-empty string")
    normalized_code = code.strip().upper()

    raw_user, owner_id = await resolve_owner(
        client, telegram_id=telegram_id, user_id=user_id
    )

    found_promo: dict[str, Any] | None = None
    lookup_incomplete = False

    for page in range(_MAX_PAGES):
        offset = page * _PAGE_LIMIT
        res = await client.list_promocodes(limit=_PAGE_LIMIT, offset=offset)
        items = res.get("items") if isinstance(res, dict) else []
        total = res.get("total") if isinstance(res, dict) else 0

        if not isinstance(items, list):
            items = []
        if not isinstance(total, int) or isinstance(total, bool):
            total = len(items)

        for item in items:
            if not isinstance(item, dict):
                continue
            item_code = item.get("code")
            if isinstance(item_code, str) and item_code.strip().upper() == normalized_code:
                found_promo = item
                break

        if found_promo is not None:
            break

        if len(items) < _PAGE_LIMIT or (offset + len(items)) >= total:
            # Full catalog searched, not found
            lookup_incomplete = False
            break
    else:
        # Loop ended after _MAX_PAGES without finding match
        lookup_incomplete = True

    data = sanitize_promocode(
        found_promo, normalized_code, lookup_incomplete=lookup_incomplete
    )
    return make_success_envelope("bedolaga_promocode_check", data)
