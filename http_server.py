#!/usr/bin/env python3
"""MCP StreamableHTTP server for Bedolaga — serves the bedolaga_balance tool over HTTP on port 3100."""

import os
import sys

import uvicorn
from mcp.server.fastmcp import FastMCP

# Add project root to path so we can import from bedolaga_server
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bedolaga_server import get_user_by_telegram_id


# Create the FastMCP server
mcp = FastMCP(
    name="bedolaga-mcp",
    json_response=True,
    stateless_http=False,
    streamable_http_path="/mcp",
)


@mcp.tool()
def bedolaga_balance(telegram_id: int) -> str:
    """Get user balance from Bedolaga bot by Telegram ID. Returns balance in rubles.

    Args:
        telegram_id: Telegram user ID
    """
    user = get_user_by_telegram_id(telegram_id)
    if user is None:
        return "Error: BEDOLAGA_API_URL and BEDOLAGA_API_KEY not configured"

    if "error" in user:
        return f"API error: {user['error']}"

    rubles = user.get("balance_rubles", 0)
    kopeks = user.get("balance_kopeks", 0)
    username = user.get("username") or user.get("first_name") or f"ID:{telegram_id}"
    status = user.get("status", "unknown")

    return f"💰 {username}: {rubles:.2f} ₽ (status: {status})"


@mcp.tool()
def bedolaga_subscription(telegram_id: int) -> str:
    """Get user subscription status from Bedolaga bot by Telegram ID.

    Returns tariff, period, and active status of the user's subscription.
    This is a readonly tool — no data is modified.

    Args:
        telegram_id: Telegram user ID
    """
    user = get_user_by_telegram_id(telegram_id)
    if user is None:
        return "Error: BEDOLAGA_API_URL and BEDOLAGA_API_KEY not configured"

    if "error" in user:
        return f"API error: {user['error']}"

    username = user.get("username") or user.get("first_name") or f"ID:{telegram_id}"
    subscription = user.get("subscription")

    if subscription is None or not isinstance(subscription, dict):
        return f"📋 {username}: no subscription"

    tariff = subscription.get("tariff", "unknown")
    period = subscription.get("period", "unknown")
    active = subscription.get("active", False)
    active_str = "✅ active" if active else "❌ inactive"

    return f"📋 {username}: tariff={tariff}, period={period}, {active_str}"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3100))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(mcp.streamable_http_app(), host=host, port=port, log_level="info")
