"""Sessionful Streamable HTTP transport for the Bedolaga MCP server.

Serves the MCP endpoint on the root path ``/`` so supportBot configures the
same base URL it already uses for mcp-remnawave. Per-session lifecycle
(initialize on ``POST /``, routing by ``Mcp-Session-Id``, per-session
termination via ``DELETE /``) is handled by the MCP SDK v2 session manager
that ``MCPServer.streamable_http_app()`` wires into the returned Starlette
app. The same endpoint also transparently serves the modern (2026-07-28)
protocol era for clients that negotiate it — the SDK's session manager routes
each request by its declared protocol version, so ``/`` stays a single
dual-era endpoint.

``GET /health`` is a liveness probe that only reports process status and the
server version; it performs no upstream Bedolaga request and never reveals the
base URL or the API key.

Graceful shutdown: on SIGTERM/SIGINT uvicorn stops accepting connections, runs
the Starlette lifespan (which exits the MCP session manager and closes all
active sessions) and then this module closes the shared upstream Bedolaga client.
All log output is produced by uvicorn/the MCP SDK and contains no API key, no
base URL and no tool results.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from . import __version__
from .config import load_config
from .server import SERVER_NAME, _transport_security, create_server
from .tools import close_client


def _bind_environ(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Resolve the HTTP bind env vars, falling back to the legacy ``HOST``/``PORT``.

    The new contract is ``MCP_HTTP_HOST``/``MCP_HTTP_PORT`` (supportBot sets
    these). The pre-existing Docker/desktop commands still set only
    ``PORT=3100``/``HOST=0.0.0.0`` (Dockerfile, docker-compose.yaml — owned by a
    later task), so the compatibility launcher must keep them working. This
    helper injects the legacy values (and their historical defaults) into the
    mapping passed to :func:`load_config`; ``config.py`` itself still validates
    the resolved host/port, so a genuinely missing bind setting still fails
    fast.
    """
    env = dict(os.environ if environ is None else environ)
    if not (env.get("MCP_HTTP_HOST") or "").strip():
        env["MCP_HTTP_HOST"] = (env.get("HOST") or "").strip() or "0.0.0.0"
    if not (env.get("MCP_HTTP_PORT") or "").strip():
        env["MCP_HTTP_PORT"] = (env.get("PORT") or "").strip() or "3100"
    return env


def create_app(transport_host: str = "0.0.0.0") -> Starlette:
    """Build the Starlette app for the sessionful Streamable HTTP transport.

    ``transport_host`` is the same bind host Uvicorn will listen on
    (``config.mcp_http_host`` from :func:`run`); passing it into
    ``streamable_http_app`` keeps SDK-side validation and the actual Uvicorn
    bind configuration from diverging.
    """
    server = create_server()

    @server.custom_route("/health", methods=["GET"])
    async def health(request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "UP",
                "version": __version__,
                "name": SERVER_NAME,
            }
        )

    return server.streamable_http_app(
        host=transport_host,
        streamable_http_path="/",
        json_response=True,
        stateless_http=False,
        transport_security=_transport_security(),
    )


class _BedolagaHTTPServer(uvicorn.Server):
    """uvicorn server that also closes the shared upstream client on shutdown."""

    async def _serve(self, sockets=None) -> None:
        try:
            await super()._serve(sockets)
        finally:
            await close_client()


def run() -> None:
    """Run the HTTP transport until SIGTERM/SIGINT, then shut down gracefully."""
    config = load_config(environ=_bind_environ())
    app = create_app(config.mcp_http_host)
    server = _BedolagaHTTPServer(
        uvicorn.Config(
            app,
            host=config.mcp_http_host,
            port=config.mcp_http_port,
            log_level="info",
        )
    )
    asyncio.run(server.serve())


__all__ = ["create_app", "run"]


if __name__ == "__main__":
    run()
