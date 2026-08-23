"""Regression tests for FastMCP Host-header validation."""

from __future__ import annotations

import unittest

from starlette.testclient import TestClient

from bedolaga_mcp import __version__
from bedolaga_mcp.http import create_app


INITIALIZE_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "transport-security-test", "version": "1"},
    },
}


class TransportSecurityTests(unittest.TestCase):
    def _initialize(self, host: str):
        with TestClient(create_app(), raise_server_exceptions=False) as client:
            return client.post(
                "/",
                headers={
                    "Host": host,
                    "Accept": "application/json, text/event-stream",
                },
                json=INITIALIZE_REQUEST,
            )

    def test_accepts_docker_compose_service_host(self):
        response = self._initialize("bedolaga-mcp:3100")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["serverInfo"]["name"], "bedolaga-mcp")
        self.assertEqual(response.json()["result"]["serverInfo"]["version"], __version__)

    def test_keeps_rejecting_untrusted_hosts(self):
        response = self._initialize("attacker.example:3100")

        self.assertEqual(response.status_code, 421)
        self.assertEqual(response.text, "Invalid Host header")


if __name__ == "__main__":
    unittest.main()
