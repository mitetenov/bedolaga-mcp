from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp.sanitize import (
    sanitize_billing,
    sanitize_referrals,
    sanitize_subscriptions,
    sanitize_user,
)


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        result = set(value)
        for child in value.values():
            result.update(_all_keys(child))
        return result
    if isinstance(value, list):
        result: set[str] = set()
        for child in value:
            result.update(_all_keys(child))
        return result
    return set()


class SanitizerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user = {
            "id": 42,
            "telegram_id": 777,
            "email": "must-not-leak@example.com",
            "username": "owner",
            "first_name": "Owner",
            "last_name": "User",
            "status": "active",
            "balance_kopeks": 35_000,
            "has_made_first_topup": True,
            "has_had_paid_subscription": True,
            "referral_code": "SAFE42",
            "referred_by_id": 9,
            "promo_group": {
                "name": "Friends",
                "server_discount_percent": 10,
                "traffic_discount_percent": 20,
                "device_discount_percent": 30,
                "internal_rule": "must-not-leak",
            },
            "subscriptions": [
                {
                    "id": 11,
                    "status": "active",
                    "actual_status": "active",
                    "is_trial": False,
                    "tariff_id": 5,
                    "tariff_name": "Plus",
                    "start_date": "2026-08-01T00:00:00Z",
                    "end_date": "2026-09-01T00:00:00Z",
                    "subscription_url": "https://must-not-leak.example",
                }
            ],
        }

    def test_user_payload_matches_real_upstream_field_names(self) -> None:
        result = sanitize_user(self.user)

        self.assertTrue(result["has_made_first_topup"])
        self.assertTrue(result["has_had_paid_subscription"])
        self.assertEqual(
            result["promo_group"],
            {
                "name": "Friends",
                "server_discount_percent": 10,
                "traffic_discount_percent": 20,
                "device_discount_percent": 30,
            },
        )
        self.assertNotIn("email", _all_keys(result))
        self.assertNotIn("referred_by_id", _all_keys(result))

    def test_billing_payload_keeps_tariff_and_canonical_diagnosis(self) -> None:
        transactions = {
            "items": [
                {
                    "id": 1,
                    "user_id": 42,
                    "type": "deposit",
                    "is_completed": True,
                    "amount_kopeks": 35_000,
                    "created_at": "2026-08-01T10:00:00+03:00",
                    "external_id": "must-not-leak",
                },
                {
                    "id": 2,
                    "user_id": 42,
                    "type": "subscription_payment",
                    "is_completed": True,
                    "amount_kopeks": -30_000,
                    "created_at": "2026-08-01T08:30:00Z",
                },
                {
                    "id": 3,
                    "user_id": 99,
                    "type": "deposit",
                    "is_completed": True,
                    "amount_kopeks": 99_999,
                    "created_at": "2026-08-01T09:00:00Z",
                },
            ]
        }

        result = sanitize_billing(self.user, transactions, limit=1)

        self.assertTrue(result["purchased_after_latest_deposit"])
        self.assertEqual(len(result["transactions"]), 1)
        self.assertEqual(result["transactions"][0]["id"], 2)
        self.assertEqual(result["bot_subscriptions"][0]["tariff_id"], 5)
        self.assertEqual(result["bot_subscriptions"][0]["tariff_name"], "Plus")
        self.assertNotIn("external_id", _all_keys(result))
        self.assertNotIn("subscription_url", _all_keys(result))

    def test_referral_payload_excludes_invited_user_personal_data(self) -> None:
        detail = {
            "referrer": {
                "referral_code": "SAFE42",
                "effective_referral_commission_percent": 15,
                "invited_count": 3,
                "active_referrals": 2,
                "total_earned_kopeks": 5_000,
                "month_earned_kopeks": 1_000,
            },
            "referrals": {
                "items": [
                    {
                        "telegram_id": 123,
                        "email": "third-party@example.com",
                        "username": "third-party",
                    }
                ]
            },
        }

        result = sanitize_referrals(detail, raw_user=self.user)

        self.assertEqual(result["invited_count"], 3)
        self.assertTrue(result["was_referred"])
        keys = _all_keys(result)
        self.assertNotIn("telegram_id", keys)
        self.assertNotIn("email", keys)
        self.assertNotIn("username", keys)

    def test_subscription_payload_merging_ownership_and_privacy(self) -> None:
        raw_subscriptions = [
            {
                "id": 11,
                "user_id": 42,
                "status": "active",
                "actual_status": "active",
                "is_trial": False,
                "tariff_id": 5,
                "created_at": "2026-07-31T12:00:00Z",
                "start_date": "2026-08-01T00:00:00Z",
                "end_date": "2026-09-01T00:00:00Z",
                "autopay_enabled": True,
                "autopay_days_before": 3,
                "subscription_url": "https://secret.url",
                "subscription_crypto_link": "vless://secret",
                "connected_squads": ["squad1"],
                "traffic_limit_gb": 100,
                "device_limit": 2,
            },
            {
                "id": 99,
                "user_id": 999,  # different user
                "status": "active",
                "tariff_id": 1,
            },
            {
                "id": 10,
                "user_id": 42,
                "status": "expired",
                "actual_status": "expired",
                "is_trial": True,
                "tariff_id": 3,
                "created_at": "2026-06-01T12:00:00Z",
                "start_date": "2026-06-01T12:00:00Z",
                "end_date": "2026-07-01T12:00:00Z",
            },
        ]

        result = sanitize_subscriptions(self.user, raw_subscriptions, owner_id=42)

        self.assertTrue(result["has_subscription_records"])
        self.assertEqual(result["active_record_count"], 1)
        self.assertEqual(len(result["subscriptions"]), 2)

        # active first
        self.assertEqual(result["subscriptions"][0]["id"], 11)
        self.assertEqual(result["subscriptions"][0]["tariff_name"], "Plus")
        self.assertEqual(result["subscriptions"][0]["created_at"], "2026-07-31T12:00:00Z")
        self.assertEqual(result["subscriptions"][1]["id"], 10)

        # Privacy checks
        keys = _all_keys(result)
        self.assertNotIn("user_id", keys)
        self.assertNotIn("subscription_url", keys)
        self.assertNotIn("subscription_crypto_link", keys)
        self.assertNotIn("connected_squads", keys)
        self.assertNotIn("traffic_limit_gb", keys)
        self.assertNotIn("device_limit", keys)


if __name__ == "__main__":
    unittest.main()

