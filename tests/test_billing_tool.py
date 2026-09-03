from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp.errors import UpstreamUnavailableError
from bedolaga_mcp.tools.billing import bedolaga_billing_get


class FakeClient:
    def __init__(self) -> None:
        self.transaction_calls: list[dict[str, Any]] = []

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any]:
        return {"id": 42, "telegram_id": telegram_id, "balance_kopeks": 10_000}

    async def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        return {"id": user_id, "telegram_id": None, "balance_kopeks": 10_000}

    async def list_transactions(self, user_id: int, **kwargs: Any) -> dict[str, Any]:
        self.transaction_calls.append({"user_id": user_id, **kwargs})
        transaction_type = kwargs.get("type")
        if transaction_type == "deposit":
            return {
                "items": [
                    {
                        "id": 1,
                        "user_id": user_id,
                        "type": "deposit",
                        "is_completed": True,
                        "amount_kopeks": 10_000,
                        "created_at": "2026-08-01T07:00:00Z",
                    }
                ]
            }
        if transaction_type == "subscription_payment":
            return {
                "items": [
                    {
                        "id": 2,
                        "user_id": user_id,
                        "type": "subscription_payment",
                        "is_completed": True,
                        "amount_kopeks": -10_000,
                        "created_at": "2026-08-01T08:00:00Z",
                    }
                ]
            }
        return {"items": []}


class BillingToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_general_deposit_and_purchase_pages(self) -> None:
        client = FakeClient()

        result = await bedolaga_billing_get(client, telegram_id=777)

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "bedolaga-mcp")
        self.assertTrue(result["data"]["purchased_after_latest_deposit"])
        self.assertEqual(
            client.transaction_calls,
            [
                {"user_id": 42, "limit": 200, "offset": 0},
                {"user_id": 42, "type": "deposit", "limit": 200, "offset": 0},
                {
                    "user_id": 42,
                    "type": "subscription_payment",
                    "limit": 200,
                    "offset": 0,
                },
            ],
        )

    async def test_propagates_upstream_unavailable_from_transactions(self) -> None:
        class FailingTransactionsClient(FakeClient):
            async def list_transactions(self, user_id: int, **kwargs: Any) -> dict[str, Any]:
                raise UpstreamUnavailableError("Requested Bedolaga resource is unavailable")

        client = FailingTransactionsClient()
        with self.assertRaises(UpstreamUnavailableError) as ctx:
            await bedolaga_billing_get(client, telegram_id=777)
        self.assertEqual(ctx.exception.code, "upstream_unavailable")
        self.assertTrue(ctx.exception.retryable)


if __name__ == "__main__":
    unittest.main()
