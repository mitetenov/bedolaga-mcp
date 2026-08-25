from __future__ import annotations

import unittest
from typing import Any

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


if __name__ == "__main__":
    unittest.main()
