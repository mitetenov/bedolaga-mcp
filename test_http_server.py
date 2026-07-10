#!/usr/bin/env python3
"""Test script for bedolaga-mcp HTTP server."""
import urllib.request
import json

BASE = "http://localhost:3100/mcp"

def req(method, params=None, session_id=None):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    
    body = {
        "jsonrpc": "2.0",
        "method": method,
        "id": 1,
    }
    if params:
        body["params"] = params
    
    data = json.dumps(body).encode()
    r = urllib.request.Request(BASE, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(r, timeout=10) as resp:
        session = resp.headers.get("mcp-session-id", "")
        return json.loads(resp.read()), session

if __name__ == "__main__":
    # Step 1: Initialize
    params = {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"}
    }
    result, session_id = req("initialize", params)
    print("=== initialize ===")
    print(f"Session ID: {session_id}")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Step 2: List tools
    result, _ = req("tools/list", session_id=session_id)
    print("\n=== tools/list ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Step 3: Call tool
    result, _ = req("tools/call", params={"name": "bedolaga_balance", "arguments": {"telegram_id": 123456789}}, session_id=session_id)
    print("\n=== tools/call ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
