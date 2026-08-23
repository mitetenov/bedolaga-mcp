from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp.tools.tickets import bedolaga_tickets_get


class MockBedolagaClient:
    def __init__(
        self,
        users_by_tg: dict[int, Any] | None = None,
        tickets_by_user: dict[int, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.users_by_tg = users_by_tg or {}
        self.tickets_by_user = tickets_by_user or {}

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any]:
        return self.users_by_tg[telegram_id]

    async def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        return {"id": user_id}

    async def list_tickets(
        self, user_id: int, limit: int = 10, offset: int = 0
    ) -> list[dict[str, Any]]:
        return self.tickets_by_user.get(user_id, [])


class TicketsToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tickets_get_returns_sanitized_tickets(self) -> None:
        client: Any = MockBedolagaClient(
            users_by_tg={777: {"id": 42, "telegram_id": 777}},
            tickets_by_user={
                42: [
                    {
                        "id": 101,
                        "user_id": 42,
                        "title": "Need help with VPN",
                        "status": "open",
                        "priority": "normal",
                        "created_at": "2026-08-01T10:00:00Z",
                        "updated_at": "2026-08-01T10:30:00Z",
                        "closed_at": None,
                        "messages": [{"id": 1, "text": "Secret user message"}],
                        "media": ["photo.jpg"],
                    }
                ]
            },
        )

        res = await bedolaga_tickets_get(client, telegram_id=777, limit=10)
        self.assertTrue(res["ok"])
        self.assertEqual(res["tool"], "bedolaga_tickets_get")
        data = res["data"]
        self.assertTrue(data["has_tickets"])
        self.assertEqual(len(data["tickets"]), 1)
        ticket = data["tickets"][0]
        self.assertEqual(
            ticket,
            {
                "id": 101,
                "title": "Need help with VPN",
                "status": "open",
                "priority": "normal",
                "created_at": "2026-08-01T10:00:00Z",
                "updated_at": "2026-08-01T10:30:00Z",
                "closed_at": None,
            },
        )
        self.assertNotIn("messages", ticket)
        self.assertNotIn("media", ticket)
        self.assertNotIn("user_id", ticket)


if __name__ == "__main__":
    unittest.main()
