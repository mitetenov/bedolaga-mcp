from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp.client import BedolagaClient
from bedolaga_mcp.config import Config
from bedolaga_mcp.errors import IdentityUnavailableError, InvalidInputError
from bedolaga_mcp.tools.identity import resolve_owner, resolve_user


class MockBedolagaClient:
    def __init__(self, user_by_tg: dict[int, Any] | None = None, user_by_id: dict[int, Any] | None = None) -> None:
        self.user_by_tg = user_by_tg or {}
        self.user_by_id = user_by_id or {}
        self.called_tg: list[int] = []
        self.called_id: list[int] = []

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any]:
        self.called_tg.append(telegram_id)
        if telegram_id in self.user_by_tg:
            return self.user_by_tg[telegram_id]
        raise InvalidInputError("not found in mock")

    async def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        self.called_id.append(user_id)
        if user_id in self.user_by_id:
            return self.user_by_id[user_id]
        raise InvalidInputError("not found in mock")


class IdentityResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_exactly_one_identity(self) -> None:
        client: Any = MockBedolagaClient()
        with self.assertRaises(InvalidInputError):
            await resolve_user(client, telegram_id=None, user_id=None)
        with self.assertRaises(InvalidInputError):
            await resolve_user(client, telegram_id=123, user_id=456)
        with self.assertRaises(InvalidInputError):
            await resolve_user(client, telegram_id=True, user_id=None)  # type: ignore[arg-type]
        with self.assertRaises(InvalidInputError):
            await resolve_user(client, telegram_id=0, user_id=None)
        with self.assertRaises(InvalidInputError):
            await resolve_user(client, telegram_id=-1, user_id=None)
        with self.assertRaises(InvalidInputError):
            await resolve_user(client, telegram_id=None, user_id=False)  # type: ignore[arg-type]

    async def test_telegram_identity_calls_only_telegram_resolver(self) -> None:
        client: Any = MockBedolagaClient(user_by_tg={777: {"id": 42, "telegram_id": 777}})
        res = await resolve_user(client, telegram_id=777, user_id=None)
        self.assertEqual(res, {"id": 42, "telegram_id": 777})
        self.assertEqual(client.called_tg, [777])
        self.assertEqual(client.called_id, [])

    async def test_internal_identity_calls_only_internal_resolver(self) -> None:
        client: Any = MockBedolagaClient(user_by_id={42: {"id": 42, "telegram_id": None}})
        res = await resolve_user(client, telegram_id=None, user_id=42)
        self.assertEqual(res, {"id": 42, "telegram_id": None})
        self.assertEqual(client.called_tg, [])
        self.assertEqual(client.called_id, [42])

    async def test_resolve_owner_success(self) -> None:
        client: Any = MockBedolagaClient(user_by_tg={777: {"id": 42, "username": "alice"}})
        raw_user, owner_id = await resolve_owner(client, telegram_id=777, user_id=None)
        self.assertEqual(raw_user, {"id": 42, "username": "alice"})
        self.assertEqual(owner_id, 42)

    async def test_resolve_owner_missing_or_invalid_id_raises_identity_unavailable(self) -> None:
        client1: Any = MockBedolagaClient(user_by_tg={777: {"username": "alice"}})
        with self.assertRaises(IdentityUnavailableError):
            await resolve_owner(client1, telegram_id=777, user_id=None)

        client2: Any = MockBedolagaClient(user_by_tg={777: {"id": "42"}})
        with self.assertRaises(IdentityUnavailableError):
            await resolve_owner(client2, telegram_id=777, user_id=None)

        client3: Any = MockBedolagaClient(user_by_tg={777: {"id": -1}})
        with self.assertRaises(IdentityUnavailableError):
            await resolve_owner(client3, telegram_id=777, user_id=None)


if __name__ == "__main__":
    unittest.main()
