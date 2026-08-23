"""Real handler for the read-only ``bedolaga_referrals_get`` tool.

Resolves the caller by a system-pinned identity — exactly one of a positive
``telegram_id`` or the internal Bedolaga ``user_id`` (used for email-only
cabinet tickets) — then resolves the internal user id on the server side,
fetches the owner's referrer detail and the owner's recent ``referral_reward``
operations, and returns the sanitized referral summary.

The identity never comes from the model: both or neither argument raises
:class:`~bedolaga_mcp.errors.InvalidInputError`. Third-party identities never
reach the model: the sanitizer strips the ``referrals`` list entirely, and the
owner's own rewards are the only transaction rows shown. ``raw_user`` is passed
through so the honest ``was_referred`` flag and owner filtering work. All error
mapping happens in the registry; the handler is read-only.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..errors import InvalidInputError
from ..sanitize import REFERRAL_REWARDS_MAX, sanitize_referrals
from . import require_internal_id

#: The referrer endpoint's third-party ``referrals`` list is never returned, so
#: the smallest allowed page is enough for the owner aggregates.
_REFERRER_PAGE_LIMIT: int = 1

__all__ = ["bedolaga_referrals_get"]


async def bedolaga_referrals_get(
    client: BedolagaClient,
    *,
    telegram_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Return the current user's referral summary without third-party data.

    ``client`` is injected by the registry. Exactly one of ``telegram_id``
    (positive Telegram ID) or ``user_id`` (internal Bedolaga id) is required;
    both or neither raises ``invalid_input``. Flow: one user resolution →
    internal user id → referrer detail (owner aggregates only) → the owner's
    recent referral_reward operations → the sanitizer → the success envelope.
    """
    if (telegram_id is None) == (user_id is None):
        raise InvalidInputError("Provide exactly one of telegram_id or user_id")
    raw_user = (
        await client.get_user_by_telegram_id(telegram_id)
        if telegram_id is not None
        else await client.get_user_by_id(user_id)
    )
    owner_id = require_internal_id(raw_user)
    raw_detail = await client.get_referrer_detail(
        owner_id, limit=_REFERRER_PAGE_LIMIT, offset=0
    )
    raw_rewards = await client.list_transactions(
        owner_id, type="referral_reward", limit=REFERRAL_REWARDS_MAX, offset=0
    )
    data = sanitize_referrals(
        raw_detail, raw_user=raw_user, raw_referral_transactions=raw_rewards
    )
    return make_success_envelope("bedolaga_referrals_get", data)
