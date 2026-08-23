"""Allowlist-based sanitizers that build safe, normalized tool payloads.

The safety guarantee: outputs are built by **including only explicitly allowed
fields**, never by taking a whole upstream payload and deleting a few known
dangerous fields. If Bedolaga adds a new field tomorrow, no allowlist builder
can accidentally expose it to the LLM.

Every sanitizer is pure: it takes raw upstream payloads (dicts in the shapes
pinned in upstream-contract.md) and returns a fresh, explicitly-constructed
dict. Forbidden fields never pass through: email, ``subscription_url``,
``subscription_crypto_link``, ``external_id``, receipt identifiers/data,
Remnawave IDs/UUIDs, connection credentials/keys, connected squads,
traffic/device-limit fields, and any personal data of invited users. Financial
history is always capped at ``limit`` (or a fixed cap) so the full volume is
never returned even when upstream returns more.
"""

from __future__ import annotations

from typing import Any

from . import contracts

#: Cap for the most recent referral_reward operations shown in the referral
#: payload (the referral tool takes no limit input, so this fixed bound applies).
REFERRAL_REWARDS_MAX: int = 20

#: Fallback history cap used when ``limit`` is not a positive integer.
_DEFAULT_HISTORY_LIMIT: int = 20


def sanitize_user(raw_user: dict[str, Any]) -> dict[str, Any]:
    """Build the safe ``bedolaga_user_get`` payload from a raw UserResponse.

    Returns the current user's account facts only: balance in kopeks+rubles,
    first-topup / paid-subscription flags, referral code and a boolean
    invitation flag, safe promo-group discounts, and creation/activity dates.
    Email, internal ``referred_by_id``, subscription links, Remnawave
    identifiers and any configuration fields never appear.
    """
    balance = contracts.balance_money(raw_user.get("balance_kopeks"))
    return {
        "found": True,
        "telegram_id": raw_user.get("telegram_id"),
        "display_name": _display_name(raw_user),
        "status": raw_user.get("status"),
        "balance_kopeks": balance["balance_kopeks"] if balance else None,
        "balance_rubles": balance["balance_rubles"] if balance else None,
        "has_made_first_topup": raw_user.get("has_made_first_topup"),
        "has_had_paid_subscription": raw_user.get("has_had_paid_subscription"),
        "referral_code": raw_user.get("referral_code"),
        "was_referred": raw_user.get("referred_by_id") is not None,
        "promo_group": _promo_group(raw_user.get("promo_group")),
        "created_at": raw_user.get("created_at"),
        "last_activity": raw_user.get("last_activity"),
    }


def sanitize_billing(
    raw_user: dict[str, Any],
    raw_transactions: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    """Build the safe ``bedolaga_billing_get`` payload.

    Returns the balance, a recent transaction list sorted newest-first and
    capped at ``limit``, per-transaction normalized fields, the latest-completed
    deposit / subscription-purchase summaries, ``purchased_after_latest_deposit``
    and the bot-side subscription records with ``bot_record_status`` + Remnawave
    note. Summaries are computed over the full owned transaction set (so an
    older deposit still counts), while the returned ``transactions`` list is
    always capped at ``limit``.
    """
    owned = _owned_transactions(raw_user, raw_transactions)
    recent = sorted(owned, key=contracts.transaction_time_key, reverse=True)[
        :_history_limit(limit)
    ]
    balance = contracts.balance_money(raw_user.get("balance_kopeks"))
    return {
        "balance_kopeks": balance["balance_kopeks"] if balance else None,
        "balance_rubles": balance["balance_rubles"] if balance else None,
        "transactions": [_sanitize_transaction(tx) for tx in recent],
        "latest_completed_deposit": contracts.latest_completed_deposit(owned),
        "latest_completed_subscription_purchase": (
            contracts.latest_completed_subscription_purchase(owned)
        ),
        "purchased_after_latest_deposit": contracts.purchased_after_latest_deposit(
            owned
        ),
        "bot_subscriptions": contracts.bot_subscription_records(raw_user),
        "meta": contracts.BILLING_META_NOTE,
    }


def sanitize_subscriptions(
    raw_user: dict[str, Any] | None,
    raw_subscriptions: list[dict[str, Any]] | None,
    owner_id: int,
) -> dict[str, Any]:
    """Build the safe ``bedolaga_subscription_get`` payload.

    Merges lifecycle records from /subscriptions with tariff data from /users,
    enforcing ownership (records with user_id != owner_id are excluded) and
    excluding secrets (subscription URLs, crypto links, connected squads,
    traffic/device limits).

    Results are sorted effective-active first, then end_date newest-first.
    """
    tariff_map: dict[Any, dict[str, Any]] = {}
    if isinstance(raw_user, dict):
        # Extract tariff info from raw_user's subscriptions / subscription
        subs = raw_user.get("subscriptions")
        if isinstance(subs, list):
            for s in subs:
                if isinstance(s, dict) and s.get("id") is not None:
                    tariff_map[s["id"]] = {
                        "tariff_id": s.get("tariff_id"),
                        "tariff_name": s.get("tariff_name"),
                    }
        sub = raw_user.get("subscription")
        if isinstance(sub, dict) and sub.get("id") is not None:
            tariff_map.setdefault(
                sub["id"],
                {
                    "tariff_id": sub.get("tariff_id"),
                    "tariff_name": sub.get("tariff_name"),
                },
            )

    normalized: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()

    if isinstance(raw_subscriptions, list) and raw_subscriptions:
        for item in raw_subscriptions:
            if not isinstance(item, dict):
                continue
            # Ownership check: if user_id is in item and != owner_id, skip
            if item.get("user_id") is not None and item.get("user_id") != owner_id:
                continue
            rec = contracts.bot_subscription_record(item)
            if rec is None:
                continue
            rec_id = rec.get("id")
            if rec_id is not None and rec_id in seen_ids:
                continue
            if rec_id is not None:
                seen_ids.add(rec_id)
            # Fill tariff_name from user tariff_map if missing in rec
            if rec_id in tariff_map:
                t_info = tariff_map[rec_id]
                if rec.get("tariff_id") is None and t_info.get("tariff_id") is not None:
                    rec["tariff_id"] = t_info["tariff_id"]
                if rec.get("tariff_name") is None and t_info.get("tariff_name") is not None:
                    rec["tariff_name"] = t_info["tariff_name"]
            normalized.append(rec)
    elif isinstance(raw_user, dict):
        normalized = contracts.bot_subscription_records(raw_user)

    # Sort: effective-active first, then end_date newest-first
    def _sort_key(record: dict[str, Any]) -> tuple[int, float]:
        eff = record.get("bot_record_effective_status") or record.get("bot_record_status")
        is_active = 0 if eff == "active" else 1
        parsed_end = contracts.parse_timestamp(record.get("end_date"))
        ts = parsed_end.timestamp() if parsed_end is not None else float("-inf")
        # For newest-first within the same active group, negate ts
        return (is_active, -ts)

    sorted_records = sorted(normalized, key=_sort_key)
    active_count = sum(
        1
        for r in sorted_records
        if (r.get("bot_record_effective_status") or r.get("bot_record_status")) == "active"
    )

    return {
        "has_subscription_records": len(sorted_records) > 0,
        "active_record_count": active_count,
        "subscriptions": sorted_records,
        "meta": contracts.SUBSCRIPTION_META_NOTE,
    }


def sanitize_referrals(
    raw_referrer_detail: dict[str, Any],
    *,
    raw_user: dict[str, Any] | None = None,
    raw_referral_transactions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the safe ``bedolaga_referrals_get`` payload.

    Returns aggregates of the account owner ONLY (referral code, came-by-
    invitation boolean, effective commission, invited/active counts, total and
    month earned in kopeks+rubles) plus the owner's own recent referral_reward
    operations. Third-party user objects from ``referrals.items`` never pass
    through, so no telegram_id, username, name, balance or activity of invited
    users is exposed.

    ``raw_user`` is optional and is only used to compute the honest
    ``was_referred`` flag (from the owner's ``referred_by_id``) and to filter
    referral rewards by owner; ``raw_referral_transactions`` is optional and
    supplies the owner's referral_reward operations (``[]`` when absent).
    """
    referrer = raw_referrer_detail.get("referrer")
    if not isinstance(referrer, dict):
        referrer = {}
    owner_id = raw_user.get("id") if isinstance(raw_user, dict) else None

    total = contracts.total_earned_money(referrer.get("total_earned_kopeks"))
    month = contracts.month_earned_money(referrer.get("month_earned_kopeks"))

    return {
        "referral_code": referrer.get("referral_code"),
        "was_referred": _was_referred(raw_user),
        "effective_referral_commission_percent": referrer.get(
            "effective_referral_commission_percent"
        ),
        "invited_count": referrer.get("invited_count"),
        "active_referrals": referrer.get("active_referrals"),
        "total_earned_kopeks": total["total_earned_kopeks"] if total else None,
        "total_earned_rubles": total["total_earned_rubles"] if total else None,
        "month_earned_kopeks": month["month_earned_kopeks"] if month else None,
        "month_earned_rubles": month["month_earned_rubles"] if month else None,
        "recent_referral_rewards": _recent_referral_rewards(
            raw_referral_transactions, owner_id
        ),
        "meta": contracts.REFERRAL_META_NOTE,
    }


# --- Helpers ---------------------------------------------------------------


def _display_name(raw_user: dict[str, Any]) -> str | None:
    """Compose a safe display name for the current user from their own fields."""
    parts = [
        raw_user.get("first_name"),
        raw_user.get("last_name"),
    ]
    name = " ".join(p for p in parts if isinstance(p, str) and p.strip()).strip()
    if name:
        return name
    username = raw_user.get("username")
    if isinstance(username, str) and username.strip():
        return username
    return None


def _promo_group(raw_promo: Any) -> dict[str, Any] | None:
    """Safe promo-group discounts: name + the three discount percents only."""
    if not isinstance(raw_promo, dict):
        return None
    return {
        "name": raw_promo.get("name"),
        "server_discount_percent": raw_promo.get("server_discount_percent"),
        "traffic_discount_percent": raw_promo.get("traffic_discount_percent"),
        "device_discount_percent": raw_promo.get("device_discount_percent"),
    }


def _sanitize_transaction(tx: dict[str, Any]) -> dict[str, Any]:
    """Normalize one raw transaction into an explicitly-whitelisted dict.

    Contains only: transaction id, normalized category, separate credit/debit
    direction, safe original type name, absolute amount pair, payment method,
    completion flag, description and timestamps. ``external_id`` and any other
    upstream field are never copied.
    """
    amount = contracts.amount_money(tx.get("amount_kopeks"))
    return {
        "id": tx.get("id"),
        "category": contracts.transaction_category(tx.get("type")),
        "direction": contracts.transaction_direction(tx.get("type")),
        "raw_type": tx.get("type"),
        "amount_kopeks": amount["amount_kopeks"] if amount else None,
        "amount_rubles": amount["amount_rubles"] if amount else None,
        "payment_method": tx.get("payment_method"),
        "is_completed": tx.get("is_completed"),
        "description": tx.get("description"),
        "created_at": tx.get("created_at"),
        "completed_at": tx.get("completed_at"),
    }


def _owned_transactions(
    raw_user: dict[str, Any], raw_transactions: Any
) -> list[dict[str, Any]]:
    """Return the current user's transactions from a raw transactions payload.

    Filters by the owner's ``user_id`` as defense in depth; when the owner id
    is unknown, the client's upstream ``user_id`` filter is trusted.
    """
    if not isinstance(raw_transactions, dict):
        return []
    items = raw_transactions.get("items")
    if not isinstance(items, list):
        return []
    owner_id = raw_user.get("id") if isinstance(raw_user, dict) else None
    owned = []
    for tx in items:
        if not isinstance(tx, dict):
            continue
        if owner_id is not None and tx.get("user_id") != owner_id:
            continue
        owned.append(tx)
    return owned


def _recent_referral_rewards(
    raw_transactions: Any, owner_id: Any
) -> list[dict[str, Any]]:
    """The owner's most recent completed referral_reward operations."""
    if not isinstance(raw_transactions, dict):
        return []
    items = raw_transactions.get("items")
    if not isinstance(items, list):
        return []
    rewards = []
    for tx in items:
        if not isinstance(tx, dict):
            continue
        if tx.get("type") != "referral_reward" or tx.get("is_completed") is not True:
            continue
        if owner_id is not None and tx.get("user_id") != owner_id:
            continue
        rewards.append(_sanitize_transaction(tx))
    rewards.sort(key=contracts.transaction_time_key, reverse=True)
    return rewards[:REFERRAL_REWARDS_MAX]


def _was_referred(raw_user: Any) -> bool | None:
    """``True``/``False`` from the owner's referred_by_id, else ``None``.

    ``None`` is the honest indeterminate value used when the user payload was
    not provided or lacks the field, so no false conclusion is drawn.
    """
    if not isinstance(raw_user, dict):
        return None
    if "referred_by_id" not in raw_user:
        return None
    return raw_user.get("referred_by_id") is not None


def _history_limit(limit: Any) -> int:
    if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
        return limit
    return _DEFAULT_HISTORY_LIMIT


def sanitize_tickets(
    raw_tickets: list[dict[str, Any]] | None,
    owner_id: int,
) -> dict[str, Any]:
    """Build the safe ``bedolaga_tickets_get`` payload.

    Returns the caller's own tickets with status, priority, and lifecycle dates.
    Messages, reply blocks, media, attachments, and third-party tickets are
    intentionally excluded.
    """
    if not isinstance(raw_tickets, list):
        return {
            "has_tickets": False,
            "tickets": [],
            "meta": contracts.TICKETS_META_NOTE,
        }

    tickets = []
    for item in raw_tickets:
        if not isinstance(item, dict):
            continue
        if item.get("user_id") is not None and item.get("user_id") != owner_id:
            continue
        tickets.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "priority": item.get("priority"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "closed_at": item.get("closed_at"),
            }
        )

    return {
        "has_tickets": len(tickets) > 0,
        "tickets": tickets,
        "meta": contracts.TICKETS_META_NOTE,
    }


def sanitize_payment_status(
    raw_transactions: dict[str, Any] | None,
    owner_id: int,
    limit: int = 5,
) -> dict[str, Any]:
    """Build the safe ``bedolaga_payment_status_get`` payload.

    Returns the owner's financial transactions (deposit, subscription_purchase,
    gift_purchase, refund, failed_refund) with strict accounting_status
    (completed, not_completed, unknown). Excludes third-party data and provider
    secrets.
    """
    if not isinstance(raw_transactions, dict):
        return {
            "scope": "bedolaga_accounting_transactions",
            "payments": [],
            "meta": contracts.PAYMENT_STATUS_META_NOTE,
        }

    items = raw_transactions.get("items")
    if not isinstance(items, list):
        return {
            "scope": "bedolaga_accounting_transactions",
            "payments": [],
            "meta": contracts.PAYMENT_STATUS_META_NOTE,
        }

    payments = []
    for tx in items:
        if not isinstance(tx, dict):
            continue
        if tx.get("user_id") is not None and tx.get("user_id") != owner_id:
            continue
        cat = contracts.transaction_category(tx.get("type"))
        if cat not in contracts.PAYMENT_CATEGORIES:
            continue
        amount = contracts.amount_money(tx.get("amount_kopeks"))
        payments.append(
            {
                "id": tx.get("id"),
                "category": cat,
                "direction": contracts.transaction_direction(tx.get("type")),
                "raw_type": tx.get("type"),
                "amount_kopeks": amount["amount_kopeks"] if amount else None,
                "amount_rubles": amount["amount_rubles"] if amount else None,
                "payment_method": tx.get("payment_method"),
                "accounting_status": contracts.accounting_status(tx.get("is_completed")),
                "created_at": tx.get("created_at"),
                "completed_at": tx.get("completed_at"),
            }
        )

    payments.sort(key=contracts.transaction_time_key, reverse=True)
    capped_limit = _history_limit(limit)
    return {
        "scope": "bedolaga_accounting_transactions",
        "payments": payments[:capped_limit],
        "meta": contracts.PAYMENT_STATUS_META_NOTE,
    }


__all__ = [
    "REFERRAL_REWARDS_MAX",
    "sanitize_billing",
    "sanitize_payment_status",
    "sanitize_referrals",
    "sanitize_subscriptions",
    "sanitize_tickets",
    "sanitize_user",
]



