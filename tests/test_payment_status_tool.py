from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp.contracts import accounting_status
from bedolaga_mcp.tools.payment_status import bedolaga_payment_status_get


class MockBedolagaClient:
    def __init__(
        self,
        users_by_tg: dict[int, Any] | None = None,
        transactions_by_user: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self.users_by_tg = users_by_tg or {}
        self.transactions_by_user = transactions_by_user or {}
        self.transaction_calls: list[dict[str, Any]] = []

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any]:
        return self.users_by_tg[telegram_id]

    async def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        return {"id": user_id}

    async def list_transactions(
        self,
        user_id: int,
        type: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        self.transaction_calls.append(
            {"user_id": user_id, "type": type, "limit": limit, "offset": offset}
        )
        payload = self.transactions_by_user.get(user_id, {"items": []})
        items = payload.get("items", [])
        if type is not None:
            items = [item for item in items if item.get("type") == type]
        if limit is not None:
            items = items[:limit]
        return {"items": items}


class PaymentStatusToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_payment_status_get_filters_categories_and_maps_accounting_status(self) -> None:
        client: Any = MockBedolagaClient(
            users_by_tg={777: {"id": 42, "telegram_id": 777}},
            transactions_by_user={
                42: {
                    "items": [
                        {
                            "id": 1,
                            "user_id": 42,
                            "type": "deposit",
                            "is_completed": True,
                            "amount_kopeks": 50_000,
                            "payment_method": "sbp",
                            "external_id": "provider-tx-secret",
                            "description": "Provider secret note",
                            "created_at": "2026-08-01T12:00:00Z",
                            "completed_at": "2026-08-01T12:05:00Z",
                        },
                        {
                            "id": 2,
                            "user_id": 42,
                            "type": "deposit",
                            "is_completed": False,
                            "amount_kopeks": 10_000,
                            "payment_method": "card",
                            "created_at": "2026-08-01T11:00:00Z",
                            "completed_at": None,
                        },
                        {
                            "id": 3,
                            "user_id": 42,
                            "type": "referral_reward",
                            "is_completed": True,
                            "amount_kopeks": 2_000,
                            "created_at": "2026-08-01T10:00:00Z",
                        },
                    ]
                }
            },
        )

        res = await bedolaga_payment_status_get(client, telegram_id=777, limit=5)
        self.assertTrue(res["ok"])
        self.assertEqual(res["tool"], "bedolaga_payment_status_get")
        data = res["data"]
        self.assertEqual(data["scope"], "bedolaga_accounting_transactions")
        self.assertEqual(len(data["payments"]), 2)

        # Deposit 1
        p1 = data["payments"][0]
        self.assertEqual(p1["id"], 1)
        self.assertEqual(p1["category"], "deposit")
        self.assertEqual(p1["accounting_status"], "completed")
        self.assertEqual(p1["amount_rubles"], 500.0)
        self.assertNotIn("external_id", p1)

        # Deposit 2 (is_completed is False -> not_completed, NEVER failed or pending)
        p2 = data["payments"][1]
        self.assertEqual(p2["id"], 2)
        self.assertEqual(p2["accounting_status"], "not_completed")
        self.assertNotEqual(p2["accounting_status"], "pending")
        self.assertNotEqual(p2["accounting_status"], "failed")

        self.assertEqual(
            [call["type"] for call in client.transaction_calls],
            [
                "deposit",
                "subscription_payment",
                "gift_payment",
                "refund",
                "failed_refund",
            ],
        )
        self.assertTrue(all(call["limit"] == 5 for call in client.transaction_calls))

    async def test_rewards_cannot_hide_older_payment_events(self) -> None:
        rewards = [
            {
                "id": reward_id,
                "user_id": 42,
                "type": "referral_reward",
                "is_completed": True,
                "amount_kopeks": 100,
                "created_at": f"2026-08-02T12:{reward_id % 60:02d}:00Z",
            }
            for reward_id in range(1, 251)
        ]
        deposit = {
            "id": 999,
            "user_id": 42,
            "type": "deposit",
            "is_completed": True,
            "amount_kopeks": 50_000,
            "created_at": "2026-08-01T12:00:00Z",
            "completed_at": "2026-08-01T12:01:00Z",
        }
        client: Any = MockBedolagaClient(
            users_by_tg={777: {"id": 42, "telegram_id": 777}},
            transactions_by_user={42: {"items": [*rewards, deposit]}},
        )

        res = await bedolaga_payment_status_get(client, telegram_id=777, limit=5)

        self.assertEqual([item["id"] for item in res["data"]["payments"]], [999])


if __name__ == "__main__":
    unittest.main()
