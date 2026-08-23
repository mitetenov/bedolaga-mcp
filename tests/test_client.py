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


if __name__ == "__main__":
    unittest.main()
