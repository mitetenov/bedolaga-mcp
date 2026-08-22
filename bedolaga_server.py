#!/usr/bin/env python3
"""MCP server for Bedolaga bot — stdio transport.

Lists and dispatches exactly the three read-only tools defined in the single
registry :mod:`bedolaga_mcp.tools`. Keeps the legacy JSON-line stdio loop for
now; a later task migrates this entrypoint to the MCP SDK handshake.
"""

import json
import sys

from bedolaga_mcp.tools import call_tool, list_tools, make_error


def handle_request(request: dict) -> dict:
    method = request.get("method", "")

    if method == "tools/list":
        return {"tools": list_tools()}

    if method == "tools/call":
        params = request.get("params", {}) or {}
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}

        try:
            result = call_tool(tool_name, arguments)
        except KeyError:
            result = make_error(
                tool_name,
                "internal_error",
                "Unknown tool",
            )
        except Exception:
            result = make_error(
                tool_name,
                "invalid_input",
                "Invalid tool arguments",
            )

        return {
            "content": [{
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False),
            }]
        }

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
