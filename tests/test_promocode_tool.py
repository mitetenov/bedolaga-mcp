from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp.errors import InvalidInputError
from bedolaga_mcp.tools.promocode import bedolaga_promocode_check


class MockBedolagaClient:
    def __init__(
        self,
        users_by_tg: dict[int, Any] | None = None,
        promocodes_pages: list[dict[str, Any]] | None = None,
    ) -> None:
        self.users_by_tg = users_by_tg or {}
        self.promocodes_pages = promocodes_pages or []
        self.requested_offsets: list[int] = []

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any]:
        return self.users_by_tg[telegram_id]

    async def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        return {"id": user_id}

    async def list_promocodes(
        self, limit: int = 200, offset: int = 0
    ) -> dict[str, Any]:
        self.requested_offsets.append(offset)
        page_idx = offset // limit
        if page_idx < len(self.promocodes_pages):
            return self.promocodes_pages[page_idx]
        return {"items": [], "total": 0}


class PromocodeToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_promocode_found_exact_match_and_masked(self) -> None:
        client: Any = MockBedolagaClient(
            users_by_tg={777: {"id": 42, "telegram_id": 777}},
            promocodes_pages=[
                {
                    "items": [
                        {
                            "id": 1,
                            "code": "SUMMER",
                            "is_active": True,
                            "is_valid": True,
                            "type": "balance",
                            "balance_bonus_kopeks": 10_000,
                            "subscription_days": 0,
                            "traffic_gb": 0,
                            "uses_left": 12,
                            "valid_from": "2026-08-01T00:00:00Z",
                            "valid_until": "2030-01-01T00:00:00Z",
                            "created_by": "admin@example.com",
                        }
                    ],
                    "total": 1,
                }
            ],
        )

        res = await bedolaga_promocode_check(client, telegram_id=777, code=" summer ")
        self.assertTrue(res["ok"])
        self.assertEqual(res["tool"], "bedolaga_promocode_check")
        data = res["data"]
        self.assertEqual(data["scope"], "global_promocode_definition")
        self.assertEqual(data["code_masked"], "SU***ER")
        self.assertTrue(data["globally_valid"])
        self.assertIsNone(data["reason_code"])
        self.assertEqual(data["type"], "balance")
        self.assertEqual(data["balance_bonus_kopeks"], 10_000)
        self.assertEqual(data["balance_bonus_rubles"], 100.0)
        self.assertEqual(data["uses_left"], 12)
        self.assertEqual(data["user_eligibility"], "unknown")
        self.assertNotIn("created_by", data)
        self.assertNotIn("id", data)

    async def test_promocode_not_found(self) -> None:
        client: Any = MockBedolagaClient(
            users_by_tg={777: {"id": 42, "telegram_id": 777}},
            promocodes_pages=[{"items": [], "total": 0}],
        )

        res = await bedolaga_promocode_check(client, telegram_id=777, code="UNKNOWN")
        data = res["data"]
        self.assertFalse(data["globally_valid"])
        self.assertEqual(data["reason_code"], "not_found")
        self.assertEqual(data["code_masked"], "UN***WN")

    async def test_promocode_pagination_caps_at_5_pages_and_returns_lookup_incomplete(self) -> None:
        # 5 pages of 200 items without the code, total 1200
        dummy_page = {"items": [{"id": i, "code": f"CODE_{i}"} for i in range(200)], "total": 1200}
        client: Any = MockBedolagaClient(
            users_by_tg={777: {"id": 42, "telegram_id": 777}},
            promocodes_pages=[dummy_page] * 6,
        )

        res = await bedolaga_promocode_check(client, telegram_id=777, code="TARGET")
        data = res["data"]
        self.assertFalse(data["globally_valid"])
        self.assertEqual(data["reason_code"], "lookup_incomplete")
        self.assertEqual(len(client.requested_offsets), 5)

    async def test_empty_code_raises_invalid_input(self) -> None:
        client: Any = MockBedolagaClient(users_by_tg={777: {"id": 42, "telegram_id": 777}})
        with self.assertRaises(InvalidInputError):
            await bedolaga_promocode_check(client, telegram_id=777, code="   ")


if __name__ == "__main__":
    unittest.main()
