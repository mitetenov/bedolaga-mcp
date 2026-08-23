from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp.tools.gifts import bedolaga_gifts_get


class MockBedolagaClient:
    def __init__(
        self,
        users_by_tg: dict[int, Any] | None = None,
        transactions_by_user: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self.users_by_tg = users_by_tg or {}
        self.transactions_by_user = transactions_by_user or {}
        self.requested_type: str | None = None

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
        self.requested_type = type
        return self.transactions_by_user.get(user_id, {"items": []})


class GiftsToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_gifts_get_returns_accounting_only(self) -> None:
        client: Any = MockBedolagaClient(
            users_by_tg={777: {"id": 42, "telegram_id": 777}},
            transactions_by_user={
                42: {
                    "items": [
                        {
                            "id": 99,
                            "user_id": 42,
                            "type": "gift_purchase",
                            "is_completed": True,
                            "amount_kopeks": -30_000,
                            "payment_method": "balance",
                            "recipient_user_id": 12345,
                            "gift_token": "secret-token-xyz",
                            "description": "Gift for friend",
                            "created_at": "2026-08-01T12:00:00Z",
                            "completed_at": "2026-08-01T12:00:05Z",
                        }
                    ]
                }
            },
        )

        res = await bedolaga_gifts_get(client, telegram_id=777, limit=20)
        self.assertTrue(res["ok"])
        self.assertEqual(res["tool"], "bedolaga_gifts_get")
        data = res["data"]
        self.assertEqual(data["scope"], "own_gift_purchase_transactions")
        self.assertFalse(data["received_gifts_available"])
        self.assertFalse(data["activation_status_available"])
        self.assertEqual(len(data["gift_purchases"]), 1)
        gp = data["gift_purchases"][0]
        self.assertEqual(gp["id"], 99)
        self.assertEqual(gp["amount_kopeks"], 30_000)
        self.assertEqual(gp["amount_rubles"], 300.0)
        self.assertEqual(gp["payment_method"], "balance")
        self.assertEqual(gp["accounting_status"], "completed")
        self.assertEqual(gp["created_at"], "2026-08-01T12:00:00Z")
        self.assertEqual(gp["completed_at"], "2026-08-01T12:00:05Z")

        self.assertNotIn("recipient_user_id", gp)
        self.assertNotIn("gift_token", gp)
        self.assertNotIn("description", gp)
        self.assertNotIn("user_id", gp)


if __name__ == "__main__":
    unittest.main()
