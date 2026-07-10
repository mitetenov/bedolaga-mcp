#!/usr/bin/env python3
"""MCP server for Bedolaga bot — get user balance by Telegram ID."""

import json
import os
import sys
import urllib.request
import urllib.error


def get_user_by_telegram_id(telegram_id: int) -> dict | None:
    """Fetch user info from Bedolaga API by Telegram ID."""
    base_url = os.environ.get("BEDOLAGA_API_URL", "").rstrip("/")
    api_key = os.environ.get("BEDOLAGA_API_KEY", "")

    if not base_url or not api_key:
        return None

    url = f"{base_url}/users/by-telegram-id/{telegram_id}"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


def get_transactions(user_id: int) -> dict | None:
    """Fetch transaction history for a user from Bedolaga API."""
    base_url = os.environ.get("BEDOLAGA_API_URL", "").rstrip("/")
    api_key = os.environ.get("BEDOLAGA_API_KEY", "")

    if not base_url or not api_key:
        return None

    url = f"{base_url}/users/{user_id}/transactions"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


def handle_request(request: dict) -> dict:
    method = request.get("method", "")

    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "bedolaga_balance",
                    "description": "Get user balance from Bedolaga bot by Telegram ID. Returns balance in rubles.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "telegram_id": {
                                "type": "integer",
                                "description": "Telegram user ID"
                            }
                        },
                        "required": ["telegram_id"]
                    }
                },
                {
                    "name": "bedolaga_subscription",
                    "description": "Get user subscription status from Bedolaga bot by Telegram ID. Returns tariff, period, and active status. Readonly — no data is modified.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "telegram_id": {
                                "type": "integer",
                                "description": "Telegram user ID"
                            }
                        },
                        "required": ["telegram_id"]
                    }
                },
                {
                    "name": "bedolaga_transactions",
                    "description": "Get top-up transaction history for a user from Bedolaga bot by Telegram ID. Returns a list of transactions.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "telegram_id": {
                                "type": "integer",
                                "description": "Telegram user ID"
                            }
                        },
                        "required": ["telegram_id"]
                    }
                }
            ]
        }

    elif method == "tools/call":
        tool_name = request.get("params", {}).get("name", "")
        args = request.get("params", {}).get("arguments", {})

        if tool_name == "bedolaga_balance":
            tid = args.get("telegram_id")
            if not tid:
                return {"content": [{"type": "text", "text": "Error: telegram_id required"}]}

            user = get_user_by_telegram_id(int(tid))
            if user is None:
                return {"content": [{"type": "text", "text": "Error: BEDOLAGA_API_URL and BEDOLAGA_API_KEY not configured"}]}

            if "error" in user:
                return {"content": [{"type": "text", "text": f"API error: {user['error']}"}]}

            rubles = user.get("balance_rubles", 0)
            kopeks = user.get("balance_kopeks", 0)
            username = user.get("username") or user.get("first_name") or f"ID:{tid}"
            status = user.get("status", "unknown")

            return {
                "content": [{
                    "type": "text",
                    "text": f"💰 {username}: {rubles:.2f} ₽ (status: {status})"
                }]
            }

        if tool_name == "bedolaga_subscription":
            tid = args.get("telegram_id")
            if not tid:
                return {"content": [{"type": "text", "text": "Error: telegram_id required"}]}

            user = get_user_by_telegram_id(int(tid))
            if user is None:
                return {"content": [{"type": "text", "text": "Error: BEDOLAGA_API_URL and BEDOLAGA_API_KEY not configured"}]}

            if "error" in user:
                return {"content": [{"type": "text", "text": f"API error: {user['error']}"}]}

            username = user.get("username") or user.get("first_name") or f"ID:{tid}"
            subscription = user.get("subscription")

            if subscription is None or not isinstance(subscription, dict):
                return {"content": [{"type": "text", "text": f"📋 {username}: no subscription"}]}

            tariff = subscription.get("tariff", "unknown")
            period = subscription.get("period", "unknown")
            active = subscription.get("active", False)
            active_str = "✅ active" if active else "❌ inactive"

            return {
                "content": [{
                    "type": "text",
                    "text": f"📋 {username}: tariff={tariff}, period={period}, {active_str}"
                }]
            }

        if tool_name == "bedolaga_transactions":
            tid = args.get("telegram_id")
            if not tid:
                return {"content": [{"type": "text", "text": "Error: telegram_id required"}]}

            user = get_user_by_telegram_id(int(tid))
            if user is None:
                return {"content": [{"type": "text", "text": "Error: BEDOLAGA_API_URL and BEDOLAGA_API_KEY not configured"}]}

            if "error" in user:
                return {"content": [{"type": "text", "text": f"API error: {user['error']}"}]}

            user_id = user.get("id")
            if not user_id:
                return {"content": [{"type": "text", "text": f"Error: user ID not found for telegram_id {tid}"}]}

            transactions = get_transactions(user_id)
            if transactions is None:
                return {"content": [{"type": "text", "text": "Error: BEDOLAGA_API_URL and BEDOLAGA_API_KEY not configured"}]}

            if "error" in transactions:
                return {"content": [{"type": "text", "text": f"API error: {transactions['error']}"}]}

            if isinstance(transactions, list):
                if not transactions:
                    username = user.get("username") or user.get("first_name") or f"ID:{tid}"
                    return {"content": [{"type": "text", "text": f"📋 {username}: no transactions found"}]}

                username = user.get("username") or user.get("first_name") or f"ID:{tid}"
                lines = [f"📋 {username} — transactions:"]
                for t in transactions:
                    amount = t.get("amount", 0)
                    description = t.get("description") or t.get("type") or ""
                    ts = t.get("created_at") or t.get("timestamp") or ""
                    lines.append(f"  • {amount:.2f} ₽ — {description} ({ts})")
                return {"content": [{"type": "text", "text": "\n".join(lines)}]}

            return {"content": [{"type": "text", "text": json.dumps(transactions, ensure_ascii=False, indent=2)}]}

        return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}

    return {}


if __name__ == "__main__":
    # Stdio MCP protocol
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = handle_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            pass
