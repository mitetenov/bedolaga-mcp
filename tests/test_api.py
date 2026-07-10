#!/usr/bin/env python3
"""Unit tests for get_user_by_telegram_id — the API client function."""

import json
import os
import sys
import unittest
from unittest.mock import patch, Mock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bedolaga_server import get_user_by_telegram_id


class TestGetUserByTelegramId(unittest.TestCase):
    """Direct tests for the API client function — network errors, HTTP errors, success."""

    def setUp(self):
        os.environ["BEDOLAGA_API_URL"] = "https://api.bedolaga.example.com"
        os.environ["BEDOLAGA_API_KEY"] = "test-api-key"

    def tearDown(self):
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)

    def test_no_config_returns_none(self):
        """Returns None when env vars are missing."""
        os.environ.pop("BEDOLAGA_API_URL", None)
        os.environ.pop("BEDOLAGA_API_KEY", None)
        result = get_user_by_telegram_id(123)
        self.assertIsNone(result)

    def test_no_api_url_returns_none(self):
        """Returns None when BEDOLAGA_API_URL is missing."""
        os.environ.pop("BEDOLAGA_API_URL", None)
        result = get_user_by_telegram_id(123)
        self.assertIsNone(result)

    def test_no_api_key_returns_none(self):
        """Returns None when BEDOLAGA_API_KEY is missing."""
        os.environ.pop("BEDOLAGA_API_KEY", None)
        result = get_user_by_telegram_id(123)
        self.assertIsNone(result)

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_successful_retrieval_with_subscription(self, mock_urlopen):
        """Successful API call returns parsed user JSON with subscription."""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "username": "testuser",
            "first_name": "Test",
            "balance_rubles": 100,
            "subscription": {
                "tariff": "pro",
                "period": "monthly",
                "active": True,
            },
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = get_user_by_telegram_id(123)
        self.assertEqual(result["username"], "testuser")
        self.assertEqual(result["subscription"]["tariff"], "pro")
        self.assertEqual(result["subscription"]["active"], True)

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_successful_retrieval_no_subscription(self, mock_urlopen):
        """Successful API call returns user without subscription field."""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "username": "testuser",
            "balance_rubles": 50,
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = get_user_by_telegram_id(456)
        self.assertEqual(result["username"], "testuser")
        self.assertNotIn("subscription", result)

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_user_with_first_name_no_username(self, mock_urlopen):
        """User has first_name but no username — API still returns the data."""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "first_name": "Alice",
            "balance_rubles": 200,
            "subscription": {
                "tariff": "basic",
                "period": "yearly",
                "active": False,
            },
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = get_user_by_telegram_id(789)
        self.assertEqual(result["first_name"], "Alice")
        self.assertNotIn("username", result)

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_http_404_user_not_found(self, mock_urlopen):
        """HTTP 404 — returns error dict."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.bedolaga.example.com/users/by-telegram-id/999",
            code=404,
            msg="Not Found",
            hdrs=Mock(),
            fp=Mock(read=Mock(return_value=b'{"detail":"User not found"}')),
        )

        result = get_user_by_telegram_id(999)
        self.assertIn("error", result)
        self.assertIn("HTTP 404", result["error"])
        self.assertIn("User not found", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_http_500_server_error(self, mock_urlopen):
        """HTTP 500 — returns error dict."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.bedolaga.example.com/users/by-telegram-id/1",
            code=500,
            msg="Internal Server Error",
            hdrs=Mock(),
            fp=Mock(read=Mock(return_value=b"Internal error")),
        )

        result = get_user_by_telegram_id(1)
        self.assertIn("error", result)
        self.assertIn("HTTP 500", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_http_403_forbidden(self, mock_urlopen):
        """HTTP 403 — returns error dict (e.g. bad API key)."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.bedolaga.example.com/users/by-telegram-id/1",
            code=403,
            msg="Forbidden",
            hdrs=Mock(),
            fp=Mock(read=Mock(return_value=b'{"detail":"Invalid API key"}')),
        )

        result = get_user_by_telegram_id(1)
        self.assertIn("error", result)
        self.assertIn("HTTP 403", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_network_timeout(self, mock_urlopen):
        """Socket timeout — returns error dict."""
        import socket
        mock_urlopen.side_effect = socket.timeout("timed out")

        result = get_user_by_telegram_id(123)
        self.assertIn("error", result)
        self.assertIn("timed out", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_connection_refused(self, mock_urlopen):
        """Connection refused — returns error dict."""
        mock_urlopen.side_effect = ConnectionRefusedError("Connection refused")

        result = get_user_by_telegram_id(123)
        self.assertIn("error", result)
        self.assertIn("Connection refused", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_dns_resolution_failure(self, mock_urlopen):
        """DNS resolution failure — returns error dict."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("getaddrinfo failed")

        result = get_user_by_telegram_id(123)
        self.assertIn("error", result)
        self.assertIn("getaddrinfo", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_unexpected_exception(self, mock_urlopen):
        """Unexpected exception — returns error dict."""
        mock_urlopen.side_effect = ValueError("something broke")

        result = get_user_by_telegram_id(123)
        self.assertIn("error", result)
        self.assertIn("something broke", result["error"])

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_api_url_trailing_slash_stripped(self, mock_urlopen):
        """BEDOLAGA_API_URL trailing slash is stripped before building URL."""
        os.environ["BEDOLAGA_API_URL"] = "https://api.bedolaga.example.com/"
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({"username": "u"}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        get_user_by_telegram_id(42)
        call_args = mock_urlopen.call_args[0]
        self.assertEqual(call_args[0].full_url,
                         "https://api.bedolaga.example.com/users/by-telegram-id/42")

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_large_telegram_id(self, mock_urlopen):
        """Very large Telegram IDs are handled correctly."""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({"username": "biguser"}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = get_user_by_telegram_id(999999999999)
        self.assertEqual(result["username"], "biguser")

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_request_includes_api_key_header(self, mock_urlopen):
        """X-API-Key header is set on the request."""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({"username": "u"}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        get_user_by_telegram_id(1)
        call_args = mock_urlopen.call_args[0]
        self.assertEqual(call_args[0].get_header("X-api-key"), "test-api-key")

    @patch("bedolaga_server.urllib.request.urlopen")
    def test_http_error_body_truncated(self, mock_urlopen):
        """HTTP error body is truncated to 200 chars."""
        import urllib.error
        long_body = "x" * 500
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.bedolaga.example.com/users/by-telegram-id/1",
            code=400,
            msg="Bad Request",
            hdrs=Mock(),
            fp=Mock(read=Mock(return_value=long_body.encode())),
        )

        result = get_user_by_telegram_id(1)
        self.assertIn("error", result)
        self.assertLessEqual(len(result["error"]), 200 + len("HTTP 400: "))


if __name__ == "__main__":
    unittest.main()
