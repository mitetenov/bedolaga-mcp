"""Regression tests for the legacy (handshake-era) Streamable HTTP path:
Host-header validation, session lifecycle and the JSON-in-text tool contract.

These exercise the real ``MCPServer.streamable_http_app()`` dual-era app from
MCP SDK v2 (``mcp==2.0.0``) via Starlette's ``TestClient`` — no client-side SDK
objects, just raw JSON-RPC over HTTP, the way a pre-2026 client speaks to it.
"""

from __future__ import annotations

import json
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


def _call_request(request_id: int, name: str, arguments: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


_COMMON_HEADERS = {"Accept": "application/json, text/event-stream"}


class TransportSecurityTests(unittest.TestCase):
    def _initialize(self, host: str):
        with TestClient(create_app(), raise_server_exceptions=False) as client:
            return client.post(
                "/",
                headers={**_COMMON_HEADERS, "Host": host},
                json=INITIALIZE_REQUEST,
            )

    def test_accepts_docker_compose_service_host(self):
        response = self._initialize("bedolaga-mcp:3100")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["serverInfo"]["name"], "bedolaga-mcp")
        self.assertEqual(response.json()["result"]["serverInfo"]["version"], __version__)

    def test_accepts_loopback_hosts(self):
        for host in ("127.0.0.1:3100", "localhost:3100", "[::1]:3100"):
            with self.subTest(host=host):
                response = self._initialize(host)
                self.assertEqual(response.status_code, 200, response.text)

    def test_keeps_rejecting_untrusted_hosts(self):
        response = self._initialize("attacker.example:3100")

        self.assertEqual(response.status_code, 421)
        self.assertEqual(response.text, "Invalid Host header")


class LegacySessionLifecycleTests(unittest.TestCase):
    """The legacy (pre-2026) stateful Streamable HTTP session lifecycle: one
    ``Mcp-Session-Id`` per ``initialize``, and ``DELETE`` terminates only the
    session it names — a sibling session must keep working."""

    def setUp(self) -> None:
        self._client = TestClient(create_app(), raise_server_exceptions=False)
        self._client.__enter__()
        self.addCleanup(self._client.__exit__, None, None, None)

    def _headers(self, session_id: str | None = None) -> dict:
        headers = {**_COMMON_HEADERS, "Host": "bedolaga-mcp:3100"}
        if session_id is not None:
            headers["mcp-session-id"] = session_id
        return headers

    def _new_session(self) -> str:
        response = self._client.post("/", headers=self._headers(), json=INITIALIZE_REQUEST)
        self.assertEqual(response.status_code, 200, response.text)
        session_id = response.headers.get("mcp-session-id")
        self.assertTrue(session_id, "initialize must return a non-empty Mcp-Session-Id")
        return session_id

    def test_initialize_returns_a_session_and_the_release_version(self):
        response = self._client.post("/", headers=self._headers(), json=INITIALIZE_REQUEST)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("mcp-session-id"))
        self.assertEqual(response.json()["result"]["serverInfo"]["version"], "1.2.0")

    def test_delete_terminates_only_the_named_session(self):
        session_a = self._new_session()
        session_b = self._new_session()
        self.assertNotEqual(session_a, session_b)

        delete_response = self._client.delete("/", headers=self._headers(session_a))
        self.assertEqual(delete_response.status_code, 200)

        # The deleted session is gone ...
        after_delete_a = self._client.post(
            "/",
            headers=self._headers(session_a),
            json=_call_request(2, "bedolaga_user_get", {"telegram_id": 1}),
        )
        self.assertEqual(after_delete_a.status_code, 404)

        # ... but the sibling session is completely unaffected.
        after_delete_b = self._client.post(
            "/",
            headers=self._headers(session_b),
            json=_call_request(3, "bedolaga_user_get", {"telegram_id": 1}),
        )
        self.assertEqual(after_delete_b.status_code, 200)

    def test_tool_call_result_is_a_single_json_text_block(self):
        session_id = self._new_session()

        response = self._client.post(
            "/",
            headers=self._headers(session_id),
            json=_call_request(2, "bedolaga_user_get", {"telegram_id": 123456789}),
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        # structured_output=False must keep the published contract as exactly
        # one text content block carrying the JSON payload, never a separate
        # structuredContent field newly introduced by the SDK v2 migration.
        self.assertNotIn("structuredContent", result)
        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["type"], "text")
        payload = json.loads(result["content"][0]["text"])
        self.assertIn("ok", payload)
        self.assertEqual(payload["tool"], "bedolaga_user_get")


class HealthEndpointTests(unittest.TestCase):
    def test_health_exposes_no_config(self):
        with TestClient(create_app(), raise_server_exceptions=False) as client:
            response = client.get("/health", headers={"Host": "bedolaga-mcp:3100"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body.keys()), {"status", "version", "name"})
        self.assertEqual(body["status"], "UP")
        self.assertEqual(body["version"], "1.2.0")
        self.assertEqual(body["name"], "bedolaga-mcp")
        # No upstream base URL, API key, or bind host/port ever leak here.
        serialized = json.dumps(body).lower()
        for leaked in ("api_key", "api_url", "bedolaga_api", "host", "port"):
            self.assertNotIn(leaked, serialized)


if __name__ == "__main__":
    unittest.main()
