"""End-to-end coverage for the modern (2026-07-28) MCP protocol era.

MCP SDK v2's Streamable HTTP app is dual-era: the exact same ``/`` endpoint
serves pre-2026 clients over the classic initialize/session handshake
(see ``tests/test_transport_security.py``) *and* modern clients that use
``server/discover`` instead. This module drives the real
``mcp.client.client.Client`` (the SDK's own official client, ``mode="auto"``)
over real loopback HTTP against our actual ``create_app()`` Starlette app, to
prove the migration did not silently keep the endpoint handshake-only.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
import unittest
from unittest.mock import patch

import uvicorn

from bedolaga_mcp.http import create_app

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


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _RunningServer:
    """A real Uvicorn server for ``create_app()``, bound to loopback in a thread."""

    def __init__(self) -> None:
        self.port = _free_loopback_port()
        app = create_app("127.0.0.1")
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "_RunningServer":
        self._thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        if not self.server.started:
            raise RuntimeError("test uvicorn server did not start in time")
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.server.should_exit = True
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"


class ModernClientTests(unittest.TestCase):
    """Coverage: a modern official Client negotiates 2026-07-28, lists exactly
    eight tools, and successfully calls one — against real loopback HTTP."""

    def test_modern_client_negotiates_and_calls_a_tool(self) -> None:
        async def scenario() -> tuple[str, set[str], bool, int]:
            from mcp.client.client import Client

            with _RunningServer() as running:
                async with Client(running.url, mode="auto") as client:
                    negotiated = client.protocol_version
                    listed = await client.list_tools()
                    names = {tool.name for tool in listed.tools}
                    # No live BEDOLAGA_API_URL/KEY: the handler returns a safe
                    # error envelope instead of making a real network call.
                    with patch.dict(os.environ, {"BEDOLAGA_API_URL": "", "BEDOLAGA_API_KEY": ""}):
                        result = await client.call_tool(
                            "bedolaga_user_get", {"telegram_id": 123456789}
                        )
                    return negotiated, names, result.is_error, len(result.content)

        negotiated, names, is_error, content_len = asyncio.run(scenario())

        self.assertEqual(negotiated, "2026-07-28")
        self.assertEqual(names, EXPECTED_TOOLS)
        self.assertEqual(len(names), 8)
        self.assertFalse(is_error)
        self.assertEqual(content_len, 1)


if __name__ == "__main__":
    unittest.main()
