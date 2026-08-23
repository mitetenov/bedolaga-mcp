from __future__ import annotations

import unittest
from typing import Any

from bedolaga_mcp import __version__
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


class MockFastMCPServer:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def add_tool(self, handler: Any, name: str, description: str) -> None:
        self.tools[name] = {"handler": handler, "description": description}


class ToolRegistryTests(unittest.TestCase):
    def test_version_bumped_to_1_1_0(self) -> None:
        self.assertEqual(__version__, "1.1.0")

    def test_list_tools_exact_set(self) -> None:
        tools = list_tools()
        names = {t["name"] for t in tools}
        self.assertEqual(names, EXPECTED_TOOLS)
        self.assertEqual(len(tools), 8)

    def test_register_tools_exact_set(self) -> None:
        server = MockFastMCPServer()
        register_tools(server)
        self.assertEqual(set(server.tools.keys()), EXPECTED_TOOLS)
        self.assertEqual(len(server.tools), 8)

    def test_call_tool_unknown_name_raises_keyerror(self) -> None:
        with self.assertRaises(KeyError):
            call_tool("unknown_tool", {})


if __name__ == "__main__":
    unittest.main()
