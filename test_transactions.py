#!/usr/bin/env python3
"""Unit tests for bedolaga_transactions MCP tool — business logic and handlers."""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bedolaga_server
from http_server import bedolaga_transactions as http_bedolaga_transactions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user(telegram_id=123, user_id=42, username="testuser",
               first_name="Test", balance_rubles=100.0, status="active"):
    return {
        "id": user_id,
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "balance_rubles": balance_rubles,
        "status": status,
    }


def _mock_transactions(count=3):
    return [
        {
            "id": 100 + i,
            "amount": (i + 1) * 50.0,
            "description": f"Top-up #{i + 1}",
            "type": "deposit",
            "created_at": f"2026-07-0{i + 1}T12:00:00",
        }
        for i in range(count)
    ]


class MockHTTPResponse:
    """Minimal mock for urllib.request.urlopen response."""
    def __init__(self, data, status=200):
        self._data = data
        self.status = status

    def read(self):
        return json.dumps(self._data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Tests: get_user_by_telegram_id (business logic)
# ---------------------------------------------------------------------------

class TestGetUserByTelegramId(unittest.TestCase):
    def setUp(self):
        os.environ["BEDOLAGA_API_URL"] = "https://api.example.com"
        os.environ["BEDOLAGA_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_success_returns_user_dict(self, mock_urlopen):
        user = _mock_user()
        mock_urlopen.return_value = MockHTTPResponse(user)
        result = bedolaga_server.get_user_by_telegram_id(123)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["id"], 42)
        self.assertEqual(result["username"], "testuser")

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_http_404_returns_error_dict(self, mock_urlopen):
        from urllib.error import HTTPError
        error_response = MagicMock()
        error_response.read.return_value = b'{"detail": "Not found"}'
        error_response.status = 404
        mock_urlopen.side_effect = HTTPError(
            "https://api.example.com/users/by-telegram-id/999", 404,
            "Not Found", {}, error_response,
        )
        result = bedolaga_server.get_user_by_telegram_id(999)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("404", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_network_error_returns_error_dict(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("Connection refused")
        result = bedolaga_server.get_user_by_telegram_id(123)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("Connection refused", result["error"])

    def test_missing_env_vars_returns_none(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)
        result = bedolaga_server.get_user_by_telegram_id(123)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Tests: get_transactions (business logic)
# ---------------------------------------------------------------------------

class TestGetTransactions(unittest.TestCase):
    def setUp(self):
        os.environ["BEDOLAGA_API_URL"] = "https://api.example.com"
        os.environ["BEDOLAGA_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_success_returns_transactions_list(self, mock_urlopen):
        txs = _mock_transactions(count=2)
        mock_urlopen.return_value = MockHTTPResponse(txs)
        result = bedolaga_server.get_transactions(42)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_empty_list_returns_empty_list(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse([])
        result = bedolaga_server.get_transactions(42)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_http_error_returns_error_dict(self, mock_urlopen):
        from urllib.error import HTTPError
        error_response = MagicMock()
        error_response.read.return_value = b'{"detail": "Server error"}'
        error_response.status = 500
        mock_urlopen.side_effect = HTTPError(
            "https://api.example.com/users/42/transactions", 500,
            "Internal Error", {}, error_response,
        )
        result = bedolaga_server.get_transactions(42)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("500", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_network_error_returns_error_dict(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("Timeout")
        result = bedolaga_server.get_transactions(42)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)

    def test_missing_env_vars_returns_none(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)
        result = bedolaga_server.get_transactions(42)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Tests: handle_request — bedolaga_transactions (stdio JSON-RPC handler)
# ---------------------------------------------------------------------------

class TestHandleRequestTransactions(unittest.TestCase):
    def setUp(self):
        os.environ["BEDOLAGA_API_URL"] = "https://api.example.com"
        os.environ["BEDOLAGA_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)

    @patch("bedolaga_server.get_transactions")
    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_success_returns_formatted_transactions(self, mock_get_user, mock_get_tx):
        mock_get_user.return_value = _mock_user()
        mock_get_tx.return_value = _mock_transactions(count=2)

        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {"telegram_id": 123},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("📋 testuser — transactions:", text)
        self.assertIn("• 50.00 ₽ — Top-up #1", text)
        self.assertIn("• 100.00 ₽ — Top-up #2", text)

    @patch("bedolaga_server.get_transactions")
    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_empty_transactions_returns_no_transactions_message(self, mock_get_user, mock_get_tx):
        mock_get_user.return_value = _mock_user()
        mock_get_tx.return_value = []

        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {"telegram_id": 123},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("📋 testuser: no transactions found", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_user_not_found_api_error(self, mock_get_user):
        mock_get_user.return_value = {"error": "HTTP 404: Not found"}

        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {"telegram_id": 999},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("API error:", text)
        self.assertIn("404", text)

    def test_env_not_configured(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)

        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {"telegram_id": 123},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("not configured", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_missing_user_id_returns_error(self, mock_get_user):
        # User dict without 'id' key
        mock_get_user.return_value = {"username": "no_id_user", "first_name": "NoID"}

        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {"telegram_id": 456},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("user ID not found", text)
        self.assertIn("456", text)

    @patch("bedolaga_server.get_transactions")
    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_transactions_api_error(self, mock_get_user, mock_get_tx):
        mock_get_user.return_value = _mock_user()
        mock_get_tx.return_value = {"error": "HTTP 500: Internal server error"}

        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {"telegram_id": 123},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("API error:", text)
        self.assertIn("500", text)

    def test_missing_telegram_id_returns_error(self):
        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("telegram_id required", text)

    def test_unknown_tool_returns_error(self):
        request = {
            "method": "tools/call",
            "params": {"name": "unknown_tool", "arguments": {}},
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("Unknown tool", text)

    def test_tools_list_includes_transactions(self):
        request = {"method": "tools/list"}
        response = bedolaga_server.handle_request(request)
        tool_names = [t["name"] for t in response["tools"]]
        self.assertIn("bedolaga_transactions", tool_names)

    @patch("bedolaga_server.get_transactions")
    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_fallback_to_first_name_when_no_username(self, mock_get_user, mock_get_tx):
        user = _mock_user(username=None, first_name="FirstName")
        mock_get_user.return_value = user
        mock_get_tx.return_value = _mock_transactions(count=1)

        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {"telegram_id": 123},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn("FirstName — transactions:", text)

    @patch("bedolaga_server.get_transactions")
    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_non_list_transactions_returns_json_dump(self, mock_get_user, mock_get_tx):
        mock_get_user.return_value = _mock_user()
        mock_get_tx.return_value = {"count": 0, "items": []}  # dict, not list

        request = {
            "method": "tools/call",
            "params": {
                "name": "bedolaga_transactions",
                "arguments": {"telegram_id": 123},
            },
        }
        response = bedolaga_server.handle_request(request)
        text = response["content"][0]["text"]
        self.assertIn('"count"', text)


# ---------------------------------------------------------------------------
# Tests: http_server.py — bedolaga_transactions (FastMCP decorator)
# ---------------------------------------------------------------------------

class TestHTTPServerTransactions(unittest.TestCase):
    def setUp(self):
        os.environ["BEDOLAGA_API_URL"] = "https://api.example.com"
        os.environ["BEDOLAGA_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)

    @patch("http_server.get_transactions")
    @patch("http_server.get_user_by_telegram_id")
    def test_success_returns_formatted_transactions(self, mock_get_user, mock_get_tx):
        mock_get_user.return_value = _mock_user()
        mock_get_tx.return_value = _mock_transactions(count=3)

        result = http_bedolaga_transactions(telegram_id=123)
        self.assertIsInstance(result, str)
        self.assertIn("📋 testuser — transactions:", result)
        self.assertIn("• 50.00 ₽ — Top-up #1", result)
        self.assertIn("• 100.00 ₽ — Top-up #2", result)
        self.assertIn("• 150.00 ₽ — Top-up #3", result)

    @patch("http_server.get_transactions")
    @patch("http_server.get_user_by_telegram_id")
    def test_empty_transactions(self, mock_get_user, mock_get_tx):
        mock_get_user.return_value = _mock_user()
        mock_get_tx.return_value = []

        result = http_bedolaga_transactions(telegram_id=123)
        self.assertEqual(result, "📋 testuser: no transactions found")

    @patch("http_server.get_user_by_telegram_id")
    def test_user_not_found_api_error(self, mock_get_user):
        mock_get_user.return_value = {"error": "HTTP 404: Not found"}

        result = http_bedolaga_transactions(telegram_id=999)
        self.assertIn("API error:", result)
        self.assertIn("404", result)

    def test_env_not_configured(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)

        result = http_bedolaga_transactions(telegram_id=123)
        self.assertIn("not configured", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_missing_user_id(self, mock_get_user):
        mock_get_user.return_value = {"username": "no_id_user"}

        result = http_bedolaga_transactions(telegram_id=456)
        self.assertIn("user ID not found for telegram_id 456", result)

    @patch("http_server.get_transactions")
    @patch("http_server.get_user_by_telegram_id")
    def test_transactions_api_error(self, mock_get_user, mock_get_tx):
        mock_get_user.return_value = _mock_user()
        mock_get_tx.return_value = {"error": "HTTP 500: Server error"}

        result = http_bedolaga_transactions(telegram_id=123)
        self.assertIn("API error:", result)
        self.assertIn("500", result)

    @patch("http_server.get_transactions")
    @patch("http_server.get_user_by_telegram_id")
    def test_username_fallback_to_first_name(self, mock_get_user, mock_get_tx):
        user = _mock_user(username=None, first_name="FirstName")
        mock_get_user.return_value = user
        mock_get_tx.return_value = _mock_transactions(count=1)

        result = http_bedolaga_transactions(telegram_id=123)
        self.assertIn("FirstName", result)

    @patch("http_server.get_transactions")
    @patch("http_server.get_user_by_telegram_id")
    def test_non_list_transactions_falls_back_to_json(self, mock_get_user, mock_get_tx):
        mock_get_user.return_value = _mock_user()
        mock_get_tx.return_value = {"count": 5, "items": []}

        result = http_bedolaga_transactions(telegram_id=123)
        self.assertIn('"count"', result)
        self.assertIn("5", result)


if __name__ == "__main__":
    unittest.main()
