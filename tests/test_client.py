from __future__ import annotations

import unittest

import httpx

from bedolaga_mcp.client import BedolagaClient
from bedolaga_mcp.config import Config
from bedolaga_mcp.errors import UpstreamTimeoutError, UpstreamUnavailableError


def _config() -> Config:
    return Config(
        api_url="https://bedolaga.invalid",
        api_key="test-key",
        timeout_ms=1_000,
        mcp_http_host="127.0.0.1",
        mcp_http_port=3_100,
    )


class ClientErrorMappingTests(unittest.IsolatedAsyncioTestCase):
    async def _client_with_transport(self, transport: httpx.AsyncBaseTransport) -> BedolagaClient:
        client = BedolagaClient(_config())
        await client._client.aclose()
        client._client = httpx.AsyncClient(transport=transport)
        return client

    async def test_network_failure_is_upstream_unavailable(self) -> None:
        def fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection failed", request=request)

        client = await self._client_with_transport(httpx.MockTransport(fail))
        try:
            with self.assertRaises(UpstreamUnavailableError):
                await client.get_user_by_telegram_id(777)
        finally:
            await client.aclose()

    async def test_timeout_remains_upstream_timeout(self) -> None:
        def fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out", request=request)

        client = await self._client_with_transport(httpx.MockTransport(fail))
        try:
            with self.assertRaises(UpstreamTimeoutError):
                await client.get_user_by_telegram_id(777)
        finally:
            await client.aclose()


class ClientNewRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def _client_with_handler(self, handler: Any) -> BedolagaClient:
        client = BedolagaClient(_config())
        await client._client.aclose()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return client

    async def test_list_subscriptions_exact_request_and_response(self) -> None:
        recorded_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded_requests.append(request)
            return httpx.Response(200, json=[{"id": 1, "user_id": 42}])

        client = await self._client_with_handler(handler)
        try:
            res = await client.list_subscriptions(42, limit=200, offset=0)
            self.assertEqual(res, [{"id": 1, "user_id": 42}])
            self.assertEqual(len(recorded_requests), 1)
            req = recorded_requests[0]
            self.assertEqual(req.method, "GET")
            self.assertEqual(req.url.path, "/subscriptions")
            self.assertEqual(req.url.query.decode("ascii"), "user_id=42&limit=200&offset=0")
            self.assertEqual(req.headers.get("X-API-Key"), "test-key")
        finally:
            await client.aclose()

    async def test_list_tickets_exact_request_and_response(self) -> None:
        recorded_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded_requests.append(request)
            return httpx.Response(200, json=[{"id": 101, "user_id": 42, "status": "open"}])

        client = await self._client_with_handler(handler)
        try:
            res = await client.list_tickets(42, limit=10, offset=0)
            self.assertEqual(res, [{"id": 101, "user_id": 42, "status": "open"}])
            self.assertEqual(len(recorded_requests), 1)
            req = recorded_requests[0]
            self.assertEqual(req.method, "GET")
            self.assertEqual(req.url.path, "/tickets")
            self.assertEqual(req.url.query.decode("ascii"), "user_id=42&limit=10&offset=0")
            self.assertEqual(req.headers.get("X-API-Key"), "test-key")
        finally:
            await client.aclose()

    async def test_list_promocodes_exact_request_and_response(self) -> None:
        recorded_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded_requests.append(request)
            return httpx.Response(200, json={"items": [{"id": 5, "code": "SUMMER"}], "total": 1})

        client = await self._client_with_handler(handler)
        try:
            res = await client.list_promocodes(limit=200, offset=0)
            self.assertEqual(res, {"items": [{"id": 5, "code": "SUMMER"}], "total": 1})
            self.assertEqual(len(recorded_requests), 1)
            req = recorded_requests[0]
            self.assertEqual(req.method, "GET")
            self.assertEqual(req.url.path, "/promo-codes")
            self.assertEqual(req.url.query.decode("ascii"), "limit=200&offset=0")
            self.assertEqual(req.headers.get("X-API-Key"), "test-key")
        finally:
            await client.aclose()

    async def test_shape_rejection_for_lists_and_objects(self) -> None:
        # /subscriptions returning dict instead of list
        client1 = await self._client_with_handler(lambda req: httpx.Response(200, json={"error": "none"}))
        # /subscriptions returning list of non-dicts
        client2 = await self._client_with_handler(lambda req: httpx.Response(200, json=["not-a-dict"]))
        # /promo-codes returning list instead of dict
        client3 = await self._client_with_handler(lambda req: httpx.Response(200, json=[{"code": "A"}]))

        try:
            from bedolaga_mcp.errors import InvalidUpstreamResponseError
            with self.assertRaises(InvalidUpstreamResponseError):
                await client1.list_subscriptions(42)
            with self.assertRaises(InvalidUpstreamResponseError):
                await client2.list_subscriptions(42)
            with self.assertRaises(InvalidUpstreamResponseError):
                await client3.list_promocodes()
        finally:
            await client1.aclose()
            await client2.aclose()
            await client3.aclose()

    async def test_input_validation_rejections(self) -> None:
        client = await self._client_with_handler(lambda req: httpx.Response(200, json=[]))
        from bedolaga_mcp.errors import InvalidInputError
        try:
            # bool instead of int
            with self.assertRaises(InvalidInputError):
                await client.list_subscriptions(True)  # type: ignore[arg-type]
            with self.assertRaises(InvalidInputError):
                await client.list_subscriptions(42, limit=True)  # type: ignore[arg-type]
            with self.assertRaises(InvalidInputError):
                await client.list_subscriptions(42, offset=True)  # type: ignore[arg-type]
            # out of bounds limit
            with self.assertRaises(InvalidInputError):
                await client.list_promocodes(limit=0)
            with self.assertRaises(InvalidInputError):
                await client.list_promocodes(limit=201)
            # negative offset
            with self.assertRaises(InvalidInputError):
                await client.list_promocodes(offset=-1)
        finally:
            await client.aclose()


if __name__ == "__main__":
    unittest.main()

