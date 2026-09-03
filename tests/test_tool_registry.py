from __future__ import annotations

import logging
import unittest
import unittest.mock
from typing import Any

import httpx

from bedolaga_mcp import __version__
from bedolaga_mcp.server import create_server
from bedolaga_mcp.tools import call_tool, list_tools, register_tools

EXPECTED_TOOLS = {
    "bedolaga_user_get",
    "bedolaga_billing_get",
    "bedolaga_referrals_get",
    "bedolaga_subscription_get",
    "bedolaga_tickets_get",
    "bedolaga_payment_status_get",
    "bedolaga_promocode_check",
    "bedolaga_gifts_get",
}


class MockMCPServer:
    """Stand-in for ``mcp.server.MCPServer`` recording every ``add_tool`` call."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def add_tool(
        self,
        handler: Any,
        name: str,
        description: str,
        structured_output: bool | None = None,
    ) -> None:
        self.tools[name] = {
            "handler": handler,
            "description": description,
            "structured_output": structured_output,
        }


class ToolRegistryTests(unittest.TestCase):
    def test_version_bumped_to_1_2_0(self) -> None:
        self.assertEqual(__version__, "1.2.0")

    def test_list_tools_exact_set(self) -> None:
        tools = list_tools()
        names = {t["name"] for t in tools}
        self.assertEqual(names, EXPECTED_TOOLS)
        self.assertEqual(len(tools), 8)

    def test_register_tools_exact_set(self) -> None:
        server = MockMCPServer()
        register_tools(server)
        self.assertEqual(set(server.tools.keys()), EXPECTED_TOOLS)
        self.assertEqual(len(server.tools), 8)

    def test_register_tools_forces_unstructured_output(self) -> None:
        """Every handler must opt out of the SDK's auto-detected structured
        output so the published contract stays JSON-in-text-content, not a
        new structured schema silently introduced by the SDK migration."""
        server = MockMCPServer()
        register_tools(server)
        for name, tool in server.tools.items():
            self.assertIs(
                tool["structured_output"],
                False,
                msg=f"{name} must register with structured_output=False",
            )

    def test_call_tool_unknown_name_raises_keyerror(self) -> None:
        with self.assertRaises(KeyError):
            call_tool("unknown_tool", {})


class StdioHttpSchemaParityTests(unittest.TestCase):
    """``create_server()`` is the single factory both ``bedolaga_mcp.http`` and
    ``bedolaga_mcp.stdio`` call, so a real ``MCPServer`` built through it must
    report the exact same eight names and input schemas as the registry's own
    ``list_tools()`` — the two transports can never drift apart."""

    def test_real_mcpserver_matches_the_registry_schema_exactly(self) -> None:
        server = create_server()
        # MCPServer exposes no public "list registered tools" API (only
        # async tools/list over a transport); reaching into the private
        # _tool_manager is the only way to get the schemas synchronously for
        # this parity check. If a future SDK bump renames/removes
        # _tool_manager, this is the line that will need updating.
        registered = {tool.name: tool.parameters for tool in server._tool_manager.list_tools()}  # noqa: SLF001

        registry = {tool["name"]: tool["inputSchema"] for tool in list_tools()}

        self.assertEqual(set(registered.keys()), EXPECTED_TOOLS)
        self.assertEqual(set(registered.keys()), set(registry.keys()))
        for name in EXPECTED_TOOLS:
            self.assertEqual(
                registered[name],
                registry[name],
                msg=f"{name}: MCPServer-registered schema and list_tools() schema diverge",
            )


class ServerLoggingLevelTests(unittest.TestCase):
    """``MCPServer`` defaults to INFO and, at INFO, the SDK's own transport
    code logs raw session UUIDs on every session create/terminate
    (``streamable_http_manager.py``, ``streamable_http.py``). ``create_server``
    must keep the ``mcp`` logger at WARNING or above so that never happens,
    regardless of what a future SDK bump does to its own logging defaults."""

    def test_create_server_keeps_mcp_logger_at_warning_or_above(self) -> None:
        create_server()

        self.assertGreaterEqual(logging.getLogger("mcp").getEffectiveLevel(), logging.WARNING)


class ToolRegistryIntegrationTests(unittest.TestCase):
    def _create_client(self, handler: Any) -> BedolagaClient:
        from bedolaga_mcp.client import BedolagaClient
        from bedolaga_mcp.config import Config

        cfg = Config(
            api_url="https://bedolaga.invalid",
            api_key="secret-api-key-test",
            timeout_ms=1_000,
            mcp_http_host="127.0.0.1",
            mcp_http_port=3_100,
        )
        client = BedolagaClient(cfg)
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return client

    def test_billing_get_user_lookup_404_returns_user_not_found_envelope_and_skips_transactions(self) -> None:
        recorded_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded_requests.append(request)
            return httpx.Response(404, json={"detail": "user not found", "upstream_secret": "do_not_leak"})

        with unittest.mock.patch("bedolaga_mcp.tools._make_client", return_value=self._create_client(handler)):
            res = call_tool("bedolaga_billing_get", {"telegram_id": 777})

        self.assertFalse(res["ok"])
        self.assertEqual(res["source"], "bedolaga-mcp")
        self.assertEqual(res["tool"], "bedolaga_billing_get")
        self.assertEqual(res["error"]["code"], "user_not_found")
        self.assertFalse(res["error"]["retryable"])
        self.assertEqual(res["error"]["message"], "User not found")
        # Ensure only user lookup was attempted, never transactions
        self.assertEqual(len(recorded_requests), 1)
        self.assertEqual(recorded_requests[0].url.path, "/users/by-telegram-id/777")
        # Ensure no secrets leak
        self.assertNotIn("secret-api-key-test", str(res))
        self.assertNotIn("do_not_leak", str(res))

    def test_billing_get_user_found_transactions_404_returns_upstream_unavailable_envelope(self) -> None:
        recorded_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded_requests.append(request)
            if request.url.path == "/users/by-telegram-id/777":
                return httpx.Response(200, json={"id": 42, "telegram_id": 777, "balance_kopeks": 10_000})
            if request.url.path == "/transactions":
                return httpx.Response(404, json={"detail": "not found", "upstream_secret": "do_not_leak"})
            return httpx.Response(500, json={"detail": "unexpected"})

        with unittest.mock.patch("bedolaga_mcp.tools._make_client", return_value=self._create_client(handler)):
            res = call_tool("bedolaga_billing_get", {"telegram_id": 777})

        self.assertFalse(res["ok"])
        self.assertEqual(res["source"], "bedolaga-mcp")
        self.assertEqual(res["tool"], "bedolaga_billing_get")
        self.assertEqual(res["error"]["code"], "upstream_unavailable")
        self.assertTrue(res["error"]["retryable"])
        self.assertEqual(res["error"]["message"], "Requested Bedolaga resource is unavailable")
        # Ensure user was looked up first, then transactions was attempted
        self.assertGreaterEqual(len(recorded_requests), 2)
        self.assertEqual(recorded_requests[0].url.path, "/users/by-telegram-id/777")
        self.assertEqual(recorded_requests[1].url.path, "/transactions")
        # Ensure no secrets leak
        self.assertNotIn("secret-api-key-test", str(res))
        self.assertNotIn("do_not_leak", str(res))

    def test_billing_get_with_user_id_404_and_transactions_404(self) -> None:
        # Case 1: user_id lookup 404
        user_404_requests: list[httpx.Request] = []

        def handler_user_404(request: httpx.Request) -> httpx.Response:
            user_404_requests.append(request)
            return httpx.Response(404, json={"detail": "not found"})

        with unittest.mock.patch("bedolaga_mcp.tools._make_client", return_value=self._create_client(handler_user_404)):
            res1 = call_tool("bedolaga_billing_get", {"user_id": 42})

        self.assertEqual(res1["error"]["code"], "user_not_found")
        self.assertFalse(res1["error"]["retryable"])
        self.assertEqual(len(user_404_requests), 1)
        self.assertEqual(user_404_requests[0].url.path, "/users/42")

        # Case 2: user_id found, transactions 404
        def handler_tx_404(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/users/42":
                return httpx.Response(200, json={"id": 42, "telegram_id": None, "balance_kopeks": 10_000})
            if request.url.path == "/transactions":
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(500, json={})

        with unittest.mock.patch("bedolaga_mcp.tools._make_client", return_value=self._create_client(handler_tx_404)):
            res2 = call_tool("bedolaga_billing_get", {"user_id": 42})

        self.assertEqual(res2["error"]["code"], "upstream_unavailable")
        self.assertTrue(res2["error"]["retryable"])


if __name__ == "__main__":
    unittest.main()

