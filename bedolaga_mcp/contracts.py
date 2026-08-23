"""Pure normalization contracts and envelope shapes for Bedolaga MCP.

This module is deliberately pure: it performs no I/O, makes no HTTP calls and
imports no client, config or tools code, so it is trivially safe and reusable
anywhere in the process. It owns:

* the single success/error envelope shapes from the spec, so no tool layer
  ever composes an envelope (or an error message) by hand, plus the fixed
  error-code catalog (``ERROR_CODES`` / ``ERROR_RETRYABLE``) with per-code
  retryable flags aligned one-to-one with :mod:`bedolaga_mcp.errors`;
* money normalization to ``*_kopeks`` / ``*_rubles`` pairs — integer kopeks is
  always the source of truth and rubles are always derived as ``kopeks / 100``;
  the ambiguous float ``amount`` / ``*_rubles`` fields are never used as truth;
* the fixed Bedolaga transaction-type → category mapping with a separate
  ``credit``/``debit`` direction, where unknown future types become
  ``unknown`` while the safe original name is preserved by the caller;
* the ``latest_completed_deposit`` and ``latest_completed_subscription_purchase``
  summaries (built only from completed items of the matching type, never from
  description text) and the ``purchased_after_latest_deposit`` signal with an
  explicit indeterminate value when no completed deposit exists;
* the safe bot-side subscription record shape: ``status`` is renamed to
  ``bot_record_status`` and the upstream locally-derived effective status is
  renamed to ``bot_record_effective_status`` (both bot-side, not panel state),
  and every record carries a fixed Remnawave note, while
  subscription_url / subscription_crypto_link / connected_squads / traffic /
  device limits are excluded.

Functions are intentionally defensive and never fabricate a value: a missing
or non-integer kopeks amount yields an honest ``None`` (rendered as JSON
``null``), never a guessed number.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from .errors import SPEC_ERROR_CODES

#: Identifier of this MCP server inside every envelope.
SOURCE: Final = "bedolaga-mcp"

# --- Error-code catalog -----------------------------------------------------

#: The ten fixed error codes from the spec, as the authoritative frozenset.
#: Derived from :data:`bedolaga_mcp.errors.SPEC_ERROR_CODES` so the tool layer
#: and the error layer can never drift.
ERROR_CODES: Final[frozenset[str]] = frozenset(SPEC_ERROR_CODES)

#: Fixed per-code retryable flag. Also derived from
#: :data:`bedolaga_mcp.errors.SPEC_ERROR_CODES`; ``make_error_envelope`` uses
#: this as the single source of the flag so no call site can disagree.
ERROR_RETRYABLE: Final[dict[str, bool]] = dict(SPEC_ERROR_CODES)

# --- Envelopes -------------------------------------------------------------


def make_success_envelope(
    tool: str,
    data: dict[str, Any],
    meta: Any = None,
) -> dict[str, Any]:
    """Build the single success envelope shape from the spec."""
    return {
        "ok": True,
        "source": SOURCE,
        "tool": tool,
        "data": data,
        "meta": meta,
    }


def make_error_envelope(
    tool: str,
    code: str,
    message: str,
    retryable: bool | None = None,
) -> dict[str, Any]:
    """Build the single error envelope shape from the spec.

    ``code`` must be one of the ten fixed error codes from
    :data:`ERROR_CODES`; an unknown code raises :class:`ValueError`. The
    ``retryable`` flag is always derived from :data:`ERROR_RETRYABLE`, so every
    call site agrees per code; passing a conflicting value raises
    :class:`ValueError` instead of silently drifting.
    """
    if code not in ERROR_RETRYABLE:
        raise ValueError(f"unknown error code: {code!r}")
    derived = ERROR_RETRYABLE[code]
    if retryable is not None and retryable != derived:
        raise ValueError(
            f"retryable flag for {code!r} is fixed to {derived!r}"
        )
    return {
        "ok": False,
        "source": SOURCE,
        "tool": tool,
        "error": {
            "code": code,
            "message": message,
            "retryable": derived,
        },
    }


# --- Transaction categories and direction ---------------------------------

#: Fixed mapping from raw Bedolaga transaction type to the normalized category.
TRANSACTION_CATEGORIES: Final[dict[str, str]] = {
    "deposit": "deposit",
    "subscription_payment": "subscription_purchase",
    "gift_payment": "gift_purchase",
    "withdrawal": "withdrawal",
    "refund": "refund",
    "failed_refund": "failed_refund",
    "referral_reward": "referral_reward",
    "poll_reward": "poll_reward",
}

#: Categories considered financial payment transactions (excluding rewards/polls).
PAYMENT_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"deposit", "subscription_purchase", "gift_purchase", "refund", "failed_refund"}
)

#: Category used for any raw type not in :data:`TRANSACTION_CATEGORIES`.
UNKNOWN_CATEGORY: Final = "unknown"

#: Raw types that credit the balance.
CREDIT_TYPES: Final[frozenset[str]] = frozenset(
    {"deposit", "referral_reward", "poll_reward", "refund"}
)

#: Raw types that debit the balance.
DEBIT_TYPES: Final[frozenset[str]] = frozenset(
    {"subscription_payment", "gift_payment", "withdrawal", "failed_refund"}
)

#: Direction value for types whose credit/debit meaning is unknown.
UNKNOWN_DIRECTION: Final = "unknown"


def accounting_status(is_completed: object) -> str:
    """Map the boolean completion flag to a strict accounting status.

    Returns ``completed`` for literal ``True``, ``not_completed`` for literal
    ``False``, and ``unknown`` for anything else. Never returns 'pending',
    'failed', or 'cancelled'.
    """
    if is_completed is True:
        return "completed"
    if is_completed is False:
        return "not_completed"
    return "unknown"


def transaction_category(raw_type: Any) -> str:

    """Map a raw Bedolaga transaction type to a fixed category.

    Unknown/future types return ``unknown``; the caller preserves the safe
    original name separately so the model can still reason about it.
    """
    if isinstance(raw_type, str) and raw_type in TRANSACTION_CATEGORIES:
        return TRANSACTION_CATEGORIES[raw_type]
    return UNKNOWN_CATEGORY


def transaction_direction(raw_type: Any) -> str:
    """Return ``credit`` or ``debit`` for a raw transaction type.

    The direction is decided by the type, never by the sign of the amount, and
    an unknown type yields the honest ``unknown`` direction.
    """
    if raw_type in CREDIT_TYPES:
        return "credit"
    if raw_type in DEBIT_TYPES:
        return "debit"
    return UNKNOWN_DIRECTION


# --- Money -----------------------------------------------------------------


def money_pair(kopeks: Any) -> dict[str, Any] | None:
    """Normalize an integer kopeks amount into ``{kopeks, rubles}``.

    Rubles are always derived as ``kopeks / 100``; the upstream float rubles
    field is never used as the source of truth. Returns ``None`` (honest
    unknown) instead of fabricating a value when ``kopeks`` is missing, boolean
    or not an integer.
    """
    k = _kopeks_int(kopeks)
    if k is None:
        return None
    return {"kopeks": k, "rubles": k / 100}


def amount_money(kopeks: Any) -> dict[str, Any] | None:
    """``amount_kopeks`` / ``amount_rubles`` pair, absolute value.

    The absolute value is used so a transaction's direction carries the
    credit/debit meaning and the amount itself is never signed.
    """
    pair = money_pair(kopeks)
    if pair is None:
        return None
    k = abs(pair["kopeks"])
    return {"amount_kopeks": k, "amount_rubles": k / 100}


def balance_money(kopeks: Any) -> dict[str, Any] | None:
    """``balance_kopeks`` / ``balance_rubles`` pair for a user payload."""
    pair = money_pair(kopeks)
    if pair is None:
        return None
    return _prefixed("balance", pair)


def total_earned_money(kopeks: Any) -> dict[str, Any] | None:
    """``total_earned_kopeks`` / ``total_earned_rubles`` pair."""
    pair = money_pair(kopeks)
    if pair is None:
        return None
    return _prefixed("total_earned", pair)


def month_earned_money(kopeks: Any) -> dict[str, Any] | None:
    """``month_earned_kopeks`` / ``month_earned_rubles`` pair."""
    pair = money_pair(kopeks)
    if pair is None:
        return None
    return _prefixed("month_earned", pair)


def _kopeks_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _prefixed(prefix: str, pair: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_kopeks": pair["kopeks"], f"{prefix}_rubles": pair["rubles"]}


# --- Latest-completed summaries and purchase-after-deposit -----------------


def latest_completed_deposit(items: Any) -> dict[str, Any] | None:
    """Latest completed ``deposit`` summary, or ``None`` when none exists.

    Built only from completed ``deposit`` items (never from description text):
    amount pair, category, created_at and completed_at.
    """
    completed = _completed_of_type(items, "deposit")
    if not completed:
        return None
    return _summary_from_latest(max(completed, key=transaction_time_key), "deposit")


def latest_completed_subscription_purchase(items: Any) -> dict[str, Any] | None:
    """Latest completed ``subscription_payment`` summary, or ``None``.

    A completed ``subscription_payment`` is the only event that confirms a
    purchase; a deposit is not a purchase.
    """
    completed = _completed_of_type(items, "subscription_payment")
    if not completed:
        return None
    return _summary_from_latest(
        max(completed, key=transaction_time_key), "subscription_purchase"
    )


def purchased_after_latest_deposit(items: Any) -> bool | None:
    """Whether a completed purchase exists after the latest completed deposit.

    ``True`` — a completed ``subscription_payment`` is strictly later than the
    latest completed ``deposit``. ``False`` — a completed deposit exists but no
    purchase after it. ``None`` — the explicit indeterminate value: there is no
    completed deposit (or its timestamps are unusable), so no conclusion is
    drawn instead of returning a false ``False``.
    """
    deposit = latest_completed_deposit(items)
    if deposit is None:
        return None
    deposit_ts = _effective_timestamp(
        {"created_at": deposit.get("created_at"), "completed_at": deposit.get("completed_at")}
    )
    if deposit_ts is None:
        return None
    for tx in _completed_of_type(items, "subscription_payment"):
        tx_ts = _effective_timestamp(tx)
        if tx_ts is not None and tx_ts > deposit_ts:
            return True
    return False


def _completed_of_type(items: Any, raw_type: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return result
    for tx in items:
        if not isinstance(tx, dict):
            continue
        if tx.get("type") == raw_type and tx.get("is_completed") is True:
            result.append(tx)
    return result


_MIN_TIMESTAMP: Final = datetime.min.replace(tzinfo=UTC)


def transaction_time_key(tx: dict[str, Any]) -> tuple[datetime, datetime]:
    """Return a timezone-safe ordering key for one transaction.

    Upstream timestamps are ISO-8601 strings and can legally carry different
    UTC offsets. Comparing their textual representations can therefore invert
    chronology. Naive values are interpreted as UTC for compatibility with
    older Bedolaga payloads; malformed or missing values sort before valid
    timestamps without raising.
    """
    effective = _effective_timestamp(tx)
    completed = parse_timestamp(tx.get("completed_at"))
    return effective or _MIN_TIMESTAMP, completed or _MIN_TIMESTAMP


def _effective_timestamp(tx: dict[str, Any]) -> datetime | None:
    """Best timestamp for ordering: created_at preferred, else completed_at."""
    for field in ("created_at", "completed_at"):
        parsed = parse_timestamp(tx.get(field))
        if parsed is not None:
            return parsed
    return None


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)



def _summary_from_latest(
    latest_tx: dict[str, Any], category: str
) -> dict[str, Any]:
    amount = amount_money(latest_tx.get("amount_kopeks"))
    return {
        "amount_kopeks": amount["amount_kopeks"] if amount else None,
        "amount_rubles": amount["amount_rubles"] if amount else None,
        "category": category,
        "created_at": latest_tx.get("created_at"),
        "completed_at": latest_tx.get("completed_at"),
    }


# --- Bot-side subscription records -----------------------------------------

#: Fixed clarifying note attached to every bot-side subscription record: the
#: record is Bedolaga's internal purchase record, not the VPN panel status.
BOT_RECORD_NOTE: Final = (
    "This is the bot-side Bedolaga purchase record, not the VPN panel status. "
    "Verify the actual panel state via the separate Remnawave MCP."
)


def bot_subscription_record(raw_sub: Any) -> dict[str, Any] | None:
    """Normalize one raw SubscriptionSummary into a safe bot-side record.

    ``status`` is renamed to ``bot_record_status`` and the upstream
    locally-derived effective status is renamed to
    ``bot_record_effective_status`` (both are bot-side, not panel state); a
    fixed Remnawave note is attached. subscription_url,
    subscription_crypto_link, connected_squads, traffic_limit_gb,
    traffic_used_gb and device_limit are excluded here.
    """
    if not isinstance(raw_sub, dict):
        return None
    return {
        "id": raw_sub.get("id"),
        "bot_record_status": raw_sub.get("status"),
        "bot_record_effective_status": raw_sub.get("actual_status"),
        "is_trial": raw_sub.get("is_trial"),
        "tariff_id": raw_sub.get("tariff_id"),
        "tariff_name": raw_sub.get("tariff_name"),
        "created_at": raw_sub.get("created_at"),
        "start_date": raw_sub.get("start_date"),
        "end_date": raw_sub.get("end_date"),
        "autopay_enabled": raw_sub.get("autopay_enabled"),
        "autopay_days_before": raw_sub.get("autopay_days_before"),
        "note": BOT_RECORD_NOTE,
    }



def bot_subscription_records(raw_user: Any) -> list[dict[str, Any]]:
    """Return safe bot-side subscription records from a raw user payload.

    The pinned upstream contract exposes both ``subscriptions`` (the complete
    list) and the legacy/current ``subscription`` object. Prefer the complete
    list when it contains valid records, deduplicate it by record id, and fall
    back to the single object for older responses.
    """
    if not isinstance(raw_user, dict):
        return []

    subscriptions = raw_user.get("subscriptions")
    records = _normalized_subscription_records(subscriptions)
    if records:
        return records

    subscription = raw_user.get("subscription")
    record = bot_subscription_record(subscription)
    return [record] if record is not None else []


def _normalized_subscription_records(raw_subscriptions: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_subscriptions, list):
        return []

    records: list[dict[str, Any]] = []
    seen_ids: set[int | str] = set()
    for raw_subscription in raw_subscriptions:
        record = bot_subscription_record(raw_subscription)
        if record is None:
            continue
        record_id = record.get("id")
        if (
            isinstance(record_id, (int, str))
            and not isinstance(record_id, bool)
            and record_id in seen_ids
        ):
            continue
        if isinstance(record_id, (int, str)) and not isinstance(record_id, bool):
            seen_ids.add(record_id)
        records.append(record)
    return records


# --- Fixed meta notes ------------------------------------------------------

#: Fixed meta explanation for the billing payload: deposit vs purchase and the
#: meaning of bot-side records.
BILLING_META_NOTE: Final = (
    "deposit = a balance credit (money added to the balance), not a purchase. "
    "Only a completed subscription_payment confirms a purchase. bot_record_status "
    "is the bot-side purchase record, not the VPN panel status; verify the actual "
    "panel state via the separate Remnawave MCP."
)

#: Fixed meta explanation for the referral payload.
REFERRAL_META_NOTE: Final = (
    "Aggregates belong to the account owner only; invited users' personal data "
    "is intentionally excluded."
)

#: Fixed meta explanation for the subscription payload.
SUBSCRIPTION_META_NOTE: Final = (
    "Bedolaga subscription records are not the VPN panel status."
)

#: Fixed meta explanation for the tickets payload.
TICKETS_META_NOTE: Final = (
    "Tickets belong to the account owner only; messages and media are intentionally excluded."
)

#: Fixed meta explanation for the payment status payload.
PAYMENT_STATUS_META_NOTE: Final = (
    "This does not expose payment-provider attempt status. not_completed is not proof of pending or failure."
)

#: Fixed meta explanation for the promo code payload.
PROMOCODE_META_NOTE: Final = (
    "Global validity only; the existing API cannot check whether this user already used or may apply the code."
)


def mask_code(code: str) -> str:
    """Mask a promo code for safe diagnostic output without revealing full plaintext."""
    clean = code.strip()
    if len(clean) >= 4:
        return f"{clean[:2]}***{clean[-2:]}"
    if len(clean) >= 2:
        return f"{clean[:1]}***{clean[-1:]}"
    return "***"


__all__ = [
    "BILLING_META_NOTE",
    "BOT_RECORD_NOTE",
    "CREDIT_TYPES",
    "DEBIT_TYPES",
    "ERROR_CODES",
    "ERROR_RETRYABLE",
    "PAYMENT_CATEGORIES",
    "PAYMENT_STATUS_META_NOTE",
    "PROMOCODE_META_NOTE",
    "REFERRAL_META_NOTE",
    "SOURCE",
    "SUBSCRIPTION_META_NOTE",
    "TICKETS_META_NOTE",
    "TRANSACTION_CATEGORIES",
    "UNKNOWN_CATEGORY",
    "UNKNOWN_DIRECTION",
    "accounting_status",
    "amount_money",
    "balance_money",
    "bot_subscription_record",
    "bot_subscription_records",
    "latest_completed_deposit",
    "latest_completed_subscription_purchase",
    "make_error_envelope",
    "make_success_envelope",
    "mask_code",
    "money_pair",
    "month_earned_money",
    "parse_timestamp",
    "purchased_after_latest_deposit",
    "total_earned_money",
    "transaction_category",
    "transaction_direction",
    "transaction_time_key",
]




