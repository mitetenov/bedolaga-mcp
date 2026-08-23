from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp.contracts import make_success_envelope
from bedolaga_mcp.sanitize import sanitize_subscriptions
from bedolaga_mcp.tools.subscription import bedolaga_subscription_get


class MockBedolagaClient:
    def __init__(
        self,
        users_by_tg: dict[int, Any] | None = None,
        users_by_id: dict[int, Any] | None = None,
        subscriptions_by_user: dict[int, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.users_by_tg = users_by_tg or {}
        self.users_by_id = users_by_id or {}
        self.subscriptions_by_user = subscriptions_by_user or {}

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any]:
        return self.users_by_tg[telegram_id]

    async def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        return self.users_by_id[user_id]

    async def list_subscriptions(
        self, user_id: int, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        return self.subscriptions_by_user.get(user_id, [])


class SubscriptionToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscription_get_merges_lifecycle_dates_and_tariff(self) -> None:
        client: Any = MockBedolagaClient(
            users_by_tg={
                12345: {
                    "id": 42,
                    "telegram_id": 12345,
                    "subscriptions": [
                        {"id": 17, "tariff_id": 4, "tariff_name": "Standard"}
                    ],
                }
            },
            subscriptions_by_user={
                42: [
                    {
                        "id": 17,
                        "user_id": 42,
                        "status": "active",
                        "actual_status": "active",
                        "is_trial": False,
                        "tariff_id": 4,
                        "created_at": "2026-07-31T12:00:00Z",
                        "start_date": "2026-08-01T00:00:00Z",
                        "end_date": "2026-09-01T00:00:00Z",
                        "autopay_enabled": True,
                        "autopay_days_before": 3,
                        "subscription_url": "https://panel.example/sub/secret",
                    }
                ]
            },
        )

        res = await bedolaga_subscription_get(client, telegram_id=12345)
        self.assertTrue(res["ok"])
        self.assertEqual(res["tool"], "bedolaga_subscription_get")
        data = res["data"]
        self.assertTrue(data["has_subscription_records"])
        self.assertEqual(data["active_record_count"], 1)
        self.assertEqual(len(data["subscriptions"]), 1)
        record = data["subscriptions"][0]
        self.assertEqual(record["id"], 17)
        self.assertEqual(record["tariff_id"], 4)
        self.assertEqual(record["tariff_name"], "Standard")
        self.assertEqual(record["created_at"], "2026-07-31T12:00:00Z")
        self.assertEqual(record["start_date"], "2026-08-01T00:00:00Z")
        self.assertEqual(record["end_date"], "2026-09-01T00:00:00Z")
        self.assertNotEqual(record["created_at"], record["start_date"])
        self.assertEqual(record["autopay_enabled"], True)
        self.assertEqual(record["autopay_days_before"], 3)
        self.assertIn("note", record)
        self.assertNotIn("subscription_url", record)
        self.assertNotIn("user_id", record)


if __name__ == "__main__":
    unittest.main()
