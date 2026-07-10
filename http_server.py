#!/usr/bin/env python3
"""MCP StreamableHTTP server for Bedolaga — serves the bedolaga_balance tool over HTTP on port 3100."""

import os
import sys

import uvicorn
from mcp.server.fastmcp import FastMCP

# Add project root to path so we can import from bedolaga_server
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bedolaga_server import get_user_by_telegram_id, get_transactions


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
def bedolaga_transactions(telegram_id: int) -> str:
    """Get top-up transaction history for a user from Bedolaga bot by Telegram ID. Returns a list of transactions.

    Args:
        telegram_id: Telegram user ID
    """
    user = get_user_by_telegram_id(telegram_id)
    if user is None:
        return "Error: BEDOLAGA_API_URL and BEDOLAGA_API_KEY not configured"

    if "error" in user:
        return f"API error: {user['error']}"

    user_id = user.get("id")
    if not user_id:
        return f"Error: user ID not found for telegram_id {telegram_id}"

    transactions = get_transactions(user_id)
    if transactions is None:
        return "Error: BEDOLAGA_API_URL and BEDOLAGA_API_KEY not configured"

    if "error" in transactions:
        return f"API error: {transactions['error']}"

    if isinstance(transactions, list):
        if not transactions:
            username = user.get("username") or user.get("first_name") or f"ID:{telegram_id}"
            return f"📋 {username}: no transactions found"

        username = user.get("username") or user.get("first_name") or f"ID:{telegram_id}"
        lines = [f"📋 {username} — transactions:"]
        for t in transactions:
            amount = t.get("amount", 0)
            description = t.get("description") or t.get("type") or ""
            ts = t.get("created_at") or t.get("timestamp") or ""
            lines.append(f"  • {amount:.2f} ₽ — {description} ({ts})")
        return "\n".join(lines)

    import json
    return json.dumps(transactions, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3100))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(mcp.streamable_http_app(), host=host, port=port, log_level="info")
