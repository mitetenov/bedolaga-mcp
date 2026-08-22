"""Real handler for the read-only ``bedolaga_referrals_get`` tool.

Resolves the caller by Telegram ID, resolves the internal user id on the
server side, fetches the owner's referrer detail and the owner's recent
``referral_reward`` operations, and returns the sanitized referral summary.

Third-party identities never reach the model: the sanitizer strips the
``referrals`` list entirely, and the owner's own rewards are the only
transaction rows shown. ``raw_user`` is passed through so the honest
``was_referred`` flag and owner filtering work. All error mapping happens in
the registry; the handler is read-only.
"""

from __future__ import annotations

from typing import Any

from ..client import BedolagaClient
from ..contracts import make_success_envelope
from ..sanitize import REFERRAL_REWARDS_MAX, sanitize_referrals
from . import require_internal_id

#: The referrer endpoint's third-party ``referrals`` list is never returned, so
#: the smallest allowed page is enough for the owner aggregates.
_REFERRER_PAGE_LIMIT: int = 1

__all__ = ["bedolaga_referrals_get"]


async def bedolaga_referrals_get(
    client: BedolagaClient, telegram_id: int
) -> dict[str, Any]:
    """Return the current user's referral summary without third-party data.

    ``client`` is injected by the registry. Flow: one user resolution by
    Telegram ID → internal user id → referrer detail (owner aggregates only) →
    the owner's recent referral_reward operations → the sanitizer → the
    success envelope.
    """
    raw_user = await client.get_user_by_telegram_id(telegram_id)
    user_id = require_internal_id(raw_user)
    raw_detail = await client.get_referrer_detail(
        user_id, limit=_REFERRER_PAGE_LIMIT, offset=0
    )
    raw_rewards = await client.list_transactions(
        user_id, type="referral_reward", limit=REFERRAL_REWARDS_MAX, offset=0
    )
    data = sanitize_referrals(
        raw_detail, raw_user=raw_user, raw_referral_transactions=raw_rewards
    )
    return make_success_envelope("bedolaga_referrals_get", data)
