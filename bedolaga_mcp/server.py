"""MCP server factory shared by both transports.

The factory is the single place where the MCP server object is created: it
fixes the server name and semantic version, and registers the three read-only
tools from the single registry :mod:`bedolaga_mcp.tools`. Both the Streamable
HTTP transport (:mod:`bedolaga_mcp.http`) and the stdio transport
(:mod:`bedolaga_mcp.stdio`) build their server through :func:`create_server`,
so the two transports can never drift apart in name, version, tools or schemas.

Importing this module has no side effects: no client is created and no tool is
registered until :func:`create_server` is called by a transport entrypoint.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import __version__
from .tools import register_tools

SERVER_NAME = "bedolaga-mcp"


def create_server() -> FastMCP:
    """Build the MCP server with the three registered read-only tools.

    The server is configured for the mcp-remnawave-compatible lifecycle:
    sessionful Streamable HTTP on the root path ``/``, JSON responses, and the
    semantic version from :data:`bedolaga_mcp.__version__`.
    """
    server = FastMCP(
        name=SERVER_NAME,
        json_response=True,
        stateless_http=False,
        streamable_http_path="/",
    )
    # FastMCP does not expose a public "version" constructor argument; the
    # semantic version is carried by the underlying low-level server and
    # reported in the MCP initialize handshake via
    # ``create_initialization_options``.
    server._mcp_server.version = __version__  # type: ignore[attr-defined]
    register_tools(server)
    return server


__all__ = ["SERVER_NAME", "create_server"]
