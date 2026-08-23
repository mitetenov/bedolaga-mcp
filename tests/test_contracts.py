from __future__ import annotations

import unittest

from bedolaga_mcp.contracts import (
    bot_subscription_records,
    latest_completed_deposit,
    purchased_after_latest_deposit,
    transaction_time_key,
)


class SubscriptionContractTests(unittest.TestCase):
    def test_exposes_tariff_fields_and_excludes_panel_secrets(self) -> None:
        records = bot_subscription_records(
            {
                "subscription": {
                    "id": 17,
                    "status": "active",
                    "actual_status": "active",
                    "is_trial": False,
                    "tariff_id": 4,
                    "tariff_name": "Standard",
                    "start_date": "2026-08-01T00:00:00Z",
                    "end_date": "2026-09-01T00:00:00Z",
                    "subscription_url": "https://secret.example/sub",
                    "subscription_crypto_link": "vless://secret",
                    "connected_squads": ["secret-squad"],
                    "traffic_limit_gb": 500,
                    "device_limit": 5,
                }
            }
        )

        self.assertEqual(records[0]["tariff_id"], 4)
        self.assertEqual(records[0]["tariff_name"], "Standard")
        self.assertEqual(records[0]["bot_record_status"], "active")
        self.assertNotIn("subscription_url", records[0])
        self.assertNotIn("subscription_crypto_link", records[0])
        self.assertNotIn("connected_squads", records[0])
        self.assertNotIn("traffic_limit_gb", records[0])
        self.assertNotIn("device_limit", records[0])

    def test_prefers_complete_list_deduplicates_and_falls_back_to_single(self) -> None:
        records = bot_subscription_records(
            {
                "subscription": {"id": 1, "tariff_name": "Legacy"},
                "subscriptions": [
                    {"id": 2, "tariff_name": "Primary"},
                    {"id": 2, "tariff_name": "Duplicate"},
                    {"id": 3, "tariff_name": "Second"},
                ],
            }
        )
        self.assertEqual([record["id"] for record in records], [2, 3])
        self.assertEqual(records[0]["tariff_name"], "Primary")

        fallback = bot_subscription_records(
            {"subscription": {"id": 1, "tariff_name": "Legacy"}, "subscriptions": []}
        )
        self.assertEqual([record["id"] for record in fallback], [1])


class TransactionChronologyTests(unittest.TestCase):
    def test_compares_iso_timestamps_by_instant_not_text(self) -> None:
        deposit = {
            "id": 1,
            "type": "deposit",
            "is_completed": True,
            "created_at": "2026-08-01T10:00:00+03:00",
            "amount_kopeks": 10_000,
        }
        purchase = {
            "id": 2,
            "type": "subscription_payment",
            "is_completed": True,
            "created_at": "2026-08-01T08:30:00Z",
            "amount_kopeks": -10_000,
        }

        self.assertGreater(transaction_time_key(purchase), transaction_time_key(deposit))
        self.assertTrue(purchased_after_latest_deposit([deposit, purchase]))

    def test_latest_deposit_uses_normalized_timezone(self) -> None:
        transactions = [
            {
                "id": 1,
                "type": "deposit",
                "is_completed": True,
                "created_at": "2026-08-01T12:00:00+05:00",
                "amount_kopeks": 1_000,
            },
            {
                "id": 2,
                "type": "deposit",
                "is_completed": True,
                "created_at": "2026-08-01T08:00:00Z",
                "amount_kopeks": 2_000,
            },
        ]

        latest = latest_completed_deposit(transactions)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["amount_kopeks"], 2_000)

    def test_only_literal_true_confirms_completion(self) -> None:
        deposit = {
            "type": "deposit",
            "is_completed": "true",
            "created_at": "2026-08-01T08:00:00Z",
            "amount_kopeks": 1_000,
        }
        self.assertIsNone(latest_completed_deposit([deposit]))


if __name__ == "__main__":
    unittest.main()
