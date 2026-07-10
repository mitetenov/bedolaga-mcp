#!/usr/bin/env python3
"""Unit tests for bedolaga_subscription and bedolaga_balance FastMCP tool functions."""

import os
import sys
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from http_server import bedolaga_subscription, bedolaga_balance


class TestBedolagaSubscriptionHTTP(unittest.TestCase):
    """Tests for the HTTP server's bedolaga_subscription tool function."""

    @patch("http_server.get_user_by_telegram_id")
    def test_successful_active_subscription(self, mock_get):
        """Returns formatted string with tariff, period, active status."""
        mock_get.return_value = {
            "username": "testuser",
            "subscription": {
                "tariff": "pro",
                "period": "monthly",
                "active": True,
            },
        }
        result = bedolaga_subscription(telegram_id=123)
        self.assertIn("testuser", result)
        self.assertIn("tariff=pro", result)
        self.assertIn("period=monthly", result)
        self.assertIn("active", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_inactive_subscription(self, mock_get):
        """Returns 'inactive' when active=False."""
        mock_get.return_value = {
            "username": "testuser",
            "subscription": {
                "tariff": "basic",
                "period": "yearly",
                "active": False,
            },
        }
        result = bedolaga_subscription(telegram_id=456)
        self.assertIn("inactive", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_no_subscription_field(self, mock_get):
        """Returns 'no subscription' when user has no subscription field."""
        mock_get.return_value = {
            "username": "testuser",
            "balance_rubles": 100,
        }
        result = bedolaga_subscription(telegram_id=789)
        self.assertIn("no subscription", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_subscription_is_none(self, mock_get):
        """Returns 'no subscription' when subscription is None."""
        mock_get.return_value = {
            "username": "testuser",
            "subscription": None,
        }
        result = bedolaga_subscription(telegram_id=789)
        self.assertIn("no subscription", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_subscription_empty_dict_defaults(self, mock_get):
        """Empty subscription dict uses defaults: tariff=unknown, period=unknown, inactive."""
        mock_get.return_value = {
            "username": "testuser",
            "subscription": {},
        }
        result = bedolaga_subscription(telegram_id=1)
        self.assertIn("tariff=unknown", result)
        self.assertIn("period=unknown", result)
        self.assertIn("inactive", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_api_not_configured(self, mock_get):
        """Returns config error when API env vars are missing."""
        mock_get.return_value = None
        result = bedolaga_subscription(telegram_id=123)
        self.assertIn("not configured", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_api_http_error(self, mock_get):
        """Returns API error message for HTTP errors."""
        mock_get.return_value = {"error": "HTTP 404: not found"}
        result = bedolaga_subscription(telegram_id=999)
        self.assertIn("API error", result)
        self.assertIn("HTTP 404", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_network_error(self, mock_get):
        """Returns API error message for network-level errors."""
        mock_get.return_value = {"error": "timed out"}
        result = bedolaga_subscription(telegram_id=123)
        self.assertIn("API error", result)
        self.assertIn("timed out", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_first_name_fallback(self, mock_get):
        """Uses first_name when username is absent."""
        mock_get.return_value = {
            "first_name": "Alice",
            "subscription": {
                "tariff": "basic",
                "period": "yearly",
                "active": True,
            },
        }
        result = bedolaga_subscription(telegram_id=123)
        self.assertIn("Alice", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_fallback_to_id(self, mock_get):
        """Falls back to ID:xxx when no username or first_name."""
        mock_get.return_value = {
            "subscription": {
                "tariff": "free",
                "period": "weekly",
                "active": True,
            },
        }
        result = bedolaga_subscription(telegram_id=42)
        self.assertIn("ID:42", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_subscription_is_string_not_dict(self, mock_get):
        """Non-dict subscription treated as 'no subscription'."""
        mock_get.return_value = {
            "username": "testuser",
            "subscription": "active",
        }
        result = bedolaga_subscription(telegram_id=1)
        self.assertIn("no subscription", result)


class TestBedolagaBalanceHTTP(unittest.TestCase):
    """Tests for the HTTP server's bedolaga_balance tool function."""

    @patch("http_server.get_user_by_telegram_id")
    def test_balance_success(self, mock_get):
        """Returns formatted balance string."""
        mock_get.return_value = {
            "username": "testuser",
            "balance_rubles": 150,
            "balance_kopeks": 50,
            "status": "active",
        }
        result = bedolaga_balance(telegram_id=123)
        self.assertIn("testuser", result)
        self.assertIn("150.00", result)
        self.assertIn("active", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_balance_no_config(self, mock_get):
        """Returns error when API not configured."""
        mock_get.return_value = None
        result = bedolaga_balance(telegram_id=123)
        self.assertIn("not configured", result)

    @patch("http_server.get_user_by_telegram_id")
    def test_balance_api_error(self, mock_get):
        """Returns API error for HTTP errors."""
        mock_get.return_value = {"error": "HTTP 404: not found"}
        result = bedolaga_balance(telegram_id=999)
        self.assertIn("API error", result)
        self.assertIn("HTTP 404", result)


if __name__ == "__main__":
    unittest.main()
