#!/usr/bin/env python3
"""Unit tests for bedolaga_server MCP tools."""

import json
import unittest
from unittest.mock import patch, Mock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bedolaga_server import handle_request


class TestToolsList(unittest.TestCase):
    def test_tools_list_includes_both_tools(self):
        """tools/list should return both bedolaga_balance and bedolaga_subscription."""
        result = handle_request({"method": "tools/list"})
        self.assertIn("tools", result)
        names = [t["name"] for t in result["tools"]]
        self.assertIn("bedolaga_balance", names)
        self.assertIn("bedolaga_subscription", names)


class TestBedolagaBalance(unittest.TestCase):
    def test_balance_missing_telegram_id(self):
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_balance", "arguments": {}}
        })
        text = result["content"][0]["text"]
        self.assertIn("telegram_id required", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_balance_success(self, mock_get):
        mock_get.return_value = {
            "username": "testuser",
            "balance_rubles": 150,
            "balance_kopeks": 50,
            "status": "active",
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_balance", "arguments": {"telegram_id": 123}}
        })
        text = result["content"][0]["text"]
        self.assertIn("testuser", text)
        self.assertIn("150.00", text)
        self.assertIn("active", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_balance_no_config(self, mock_get):
        mock_get.return_value = None
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_balance", "arguments": {"telegram_id": 123}}
        })
        text = result["content"][0]["text"]
        self.assertIn("not configured", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_balance_api_error(self, mock_get):
        mock_get.return_value = {"error": "HTTP 404: not found"}
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_balance", "arguments": {"telegram_id": 999}}
        })
        text = result["content"][0]["text"]
        self.assertIn("API error", text)
        self.assertIn("HTTP 404", text)


class TestBedolagaSubscription(unittest.TestCase):
    def test_subscription_missing_telegram_id(self):
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {}}
        })
        text = result["content"][0]["text"]
        self.assertIn("telegram_id required", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_active(self, mock_get):
        mock_get.return_value = {
            "username": "testuser",
            "subscription": {
                "tariff": "pro",
                "period": "monthly",
                "active": True,
            },
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 123}}
        })
        text = result["content"][0]["text"]
        self.assertIn("testuser", text)
        self.assertIn("tariff=pro", text)
        self.assertIn("period=monthly", text)
        self.assertIn("active", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_inactive(self, mock_get):
        mock_get.return_value = {
            "username": "testuser",
            "subscription": {
                "tariff": "basic",
                "period": "yearly",
                "active": False,
            },
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 456}}
        })
        text = result["content"][0]["text"]
        self.assertIn("testuser", text)
        self.assertIn("tariff=basic", text)
        self.assertIn("period=yearly", text)
        self.assertIn("inactive", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_no_subscription_field(self, mock_get):
        mock_get.return_value = {
            "username": "testuser",
            "balance_rubles": 100,
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 789}}
        })
        text = result["content"][0]["text"]
        self.assertIn("testuser", text)
        self.assertIn("no subscription", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_none_value(self, mock_get):
        mock_get.return_value = {
            "username": "testuser",
            "subscription": None,
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 789}}
        })
        text = result["content"][0]["text"]
        self.assertIn("no subscription", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_missing_fields_defaults(self, mock_get):
        mock_get.return_value = {
            "username": "testuser",
            "subscription": {},  # empty dict, no fields
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 1}}
        })
        text = result["content"][0]["text"]
        self.assertIn("testuser", text)
        self.assertIn("tariff=unknown", text)
        self.assertIn("period=unknown", text)
        self.assertIn("inactive", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_no_config(self, mock_get):
        mock_get.return_value = None
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 123}}
        })
        text = result["content"][0]["text"]
        self.assertIn("not configured", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_api_error(self, mock_get):
        mock_get.return_value = {"error": "HTTP 404: not found"}
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 999}}
        })
        text = result["content"][0]["text"]
        self.assertIn("API error", text)
        self.assertIn("HTTP 404", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_first_name_fallback(self, mock_get):
        """User has first_name but no username — fallback is used."""
        mock_get.return_value = {
            "first_name": "Alice",
            "subscription": {
                "tariff": "basic",
                "period": "yearly",
                "active": True,
            },
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 123}}
        })
        text = result["content"][0]["text"]
        self.assertIn("Alice", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_no_name_fallback_to_id(self, mock_get):
        """User has no username or first_name — falls back to ID:xxx."""
        mock_get.return_value = {
            "subscription": {
                "tariff": "free",
                "period": "weekly",
                "active": True,
            },
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 42}}
        })
        text = result["content"][0]["text"]
        self.assertIn("ID:42", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_field_is_string(self, mock_get):
        """subscription field is a non-dict (string) — treated as no subscription."""
        mock_get.return_value = {
            "username": "testuser",
            "subscription": "active",
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 1}}
        })
        text = result["content"][0]["text"]
        self.assertIn("no subscription", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_field_is_list(self, mock_get):
        """subscription field is a non-dict (list) — treated as no subscription."""
        mock_get.return_value = {
            "username": "testuser",
            "subscription": [{"tariff": "pro"}],
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 1}}
        })
        text = result["content"][0]["text"]
        self.assertIn("no subscription", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_active_truthy_integer(self, mock_get):
        """active=1 (truthy int) — treated as active since Python truthiness applies."""
        mock_get.return_value = {
            "username": "testuser",
            "subscription": {
                "tariff": "pro",
                "period": "daily",
                "active": 1,
            },
        }
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 1}}
        })
        text = result["content"][0]["text"]
        self.assertIn("testuser", text)
        self.assertIn("active", text)

    @patch("bedolaga_server.get_user_by_telegram_id")
    def test_subscription_network_error_message(self, mock_get):
        """Network-level error (timeout) is surfaced correctly."""
        mock_get.return_value = {"error": "timed out"}
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "bedolaga_subscription", "arguments": {"telegram_id": 123}}
        })
        text = result["content"][0]["text"]
        self.assertIn("API error", text)
        self.assertIn("timed out", text)


class TestUnknownTool(unittest.TestCase):
    def test_unknown_tool(self):
        result = handle_request({
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}}
        })
        text = result["content"][0]["text"]
        self.assertIn("Unknown tool", text)


if __name__ == "__main__":
    unittest.main()
