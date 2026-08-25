"""MCP server factory shared by both transports.

The factory is the single place where the MCP server object is created: it
fixes the server name and semantic version, and registers the eight read-only
tools from the single registry :mod:`bedolaga_mcp.tools`. Both the Streamable
HTTP transport (:mod:`bedolaga_mcp.http`) and the stdio transport
(:mod:`bedolaga_mcp.stdio`) build their server through :func:`create_server`,
so the two transports can never drift apart in name, version, tools or schemas.

Importing this module has no side effects: no client is created and no tool is
registered until :func:`create_server` is called by a transport entrypoint.

Uses the native ``MCPServer`` class from Python MCP SDK v2 (``mcp==2.0.0``),
replacing the "fast" server helper class the v1 SDK exposed. Transport wiring
(Streamable HTTP bind host, JSON responses, statefulness, Host/Origin
security) lives in :func:`bedolaga_mcp.http.create_app`, not here; this
factory owns identity and tool registration only.
"""

from __future__ import annotations

import logging

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import __version__
from .tools import register_tools

SERVER_NAME = "bedolaga-mcp"

# Keep DNS-rebinding protection enabled while allowing the two legitimate ways
# this internal service is addressed: loopback for health checks/local clients,
# and its Docker Compose service name for supportBot.  Without an explicit
# policy the SDK derives one from the Streamable HTTP app's default host
# (127.0.0.1), even though Uvicorn binds this service to 0.0.0.0, and rejects
# the Docker Host header with HTTP 421 before the MCP handler sees the request.
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


def create_server() -> MCPServer:
    """Build the MCP server with the eight registered read-only tools.

    Only identity (name, semantic version from :data:`bedolaga_mcp.__version__`)
    and tool registration belong here. Transport settings — Streamable HTTP
    bind host, JSON responses, statefulness, Host/Origin security — are the
    app factory's responsibility (:func:`bedolaga_mcp.http.create_app`), so
    the same server object serves both stdio and HTTP without transport
    concerns leaking into either.
    """
    # ``MCPServer.__init__`` defaults ``log_level`` to "INFO" and calls
    # ``configure_logging(...)`` internally, which runs
    # ``logging.basicConfig(level="INFO", ...)`` — a global root-logger
    # mutation. At INFO the SDK's own transport code logs full, unredacted
    # session UUIDs on every session create/terminate
    # (``streamable_http_manager.py``, ``streamable_http.py``), which the
    # migration plan's "never log session IDs" constraint forbids. Passing
    # ``log_level="WARNING"`` here keeps ``configure_logging`` from lowering
    # the root logger below WARNING in the first place; the explicit
    # ``getLogger("mcp").setLevel(...)`` below is a second, independent belt:
    # it sets an explicit level on the ancestor logger that
    # ``getEffectiveLevel()`` finds first, so this stays correct even if a
    # future SDK version changes what ``configure_logging`` does to the root
    # logger (e.g. skips ``basicConfig`` because a handler is already
    # attached).
    server = MCPServer(
        name=SERVER_NAME,
        version=__version__,
        log_level="WARNING",
    )
    logging.getLogger("mcp").setLevel(logging.WARNING)
    register_tools(server)
    return server


__all__ = ["ALLOWED_HTTP_HOSTS", "SERVER_NAME", "_transport_security", "create_server"]
