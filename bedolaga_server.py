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
