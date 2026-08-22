#!/usr/bin/env python3
"""MCP StreamableHTTP server for Bedolaga — serves the three read-only Bedolaga tools over HTTP on port 3100."""

import os

import uvicorn
from mcp.server.fastmcp import FastMCP

from bedolaga_mcp.tools import register_tools


# Create the FastMCP server
mcp = FastMCP(
    name="bedolaga-mcp",
    json_response=True,
    stateless_http=False,
    streamable_http_path="/mcp",
)

# Register the single public tool contract (name, description, handler).
register_tools(mcp)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3100))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(mcp.streamable_http_app(), host=host, port=port, log_level="info")
