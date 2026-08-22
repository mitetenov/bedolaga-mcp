#!/usr/bin/env python3
"""Thin compatibility launcher for the stdio transport.

Runs the MCP SDK stdio handshake on the same server factory and tool registry
as the HTTP transport. All server logic lives in :mod:`bedolaga_mcp`; this file
exists so existing commands that run ``python3 bedolaga_server.py`` keep working.
"""

from bedolaga_mcp.stdio import run

if __name__ == "__main__":
    run()
