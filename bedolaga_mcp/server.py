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
from mcp.server.transport_security import TransportSecuritySettings

from . import __version__
from .tools import register_tools

SERVER_NAME = "bedolaga-mcp"

# Keep DNS-rebinding protection enabled while allowing the two legitimate ways
# this internal service is addressed: loopback for health checks/local clients,
# and its Docker Compose service name for supportBot.  Without an explicit
# policy FastMCP derives one from its constructor's default host (127.0.0.1),
# even though Uvicorn binds this service to 0.0.0.0, and rejects the Docker Host
# header with HTTP 421 before the MCP handler sees the request.
ALLOWED_HTTP_HOSTS = (
    "127.0.0.1:*",
    "localhost:*",
    "[::1]:*",
    f"{SERVER_NAME}:*",
)
ALLOWED_HTTP_ORIGINS = (
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
    f"http://{SERVER_NAME}:*",
)


def _transport_security() -> TransportSecuritySettings:
    """Return a fresh, explicit Host/Origin policy for every server instance."""
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(ALLOWED_HTTP_HOSTS),
        allowed_origins=list(ALLOWED_HTTP_ORIGINS),
    )


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
        transport_security=_transport_security(),
    )
    # FastMCP does not expose a public "version" constructor argument; the
    # semantic version is carried by the underlying low-level server and
    # reported in the MCP initialize handshake via
    # ``create_initialization_options``.
    server._mcp_server.version = __version__  # type: ignore[attr-defined]
    register_tools(server)
    return server


__all__ = ["ALLOWED_HTTP_HOSTS", "SERVER_NAME", "create_server"]
