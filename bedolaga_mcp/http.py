"""Sessionful Streamable HTTP transport for the Bedolaga MCP server.

Serves the MCP endpoint on the root path ``/`` so supportBot configures the
same base URL it already uses for mcp-remnawave. Per-session lifecycle
(initialize on ``POST /``, routing by ``Mcp-Session-Id``, per-session
termination via ``DELETE /``) is handled by the MCP SDK's session manager that
FastMCP wires into the returned Starlette app.

``GET /health`` is a liveness probe that only reports process status and the
server version; it performs no upstream Bedolaga request and never reveals the
base URL or the API key.

Graceful shutdown: on SIGTERM/SIGINT uvicorn stops accepting connections, runs
the Starlette lifespan (which exits the MCP session manager and closes all
active sessions) and then this module closes the shared upstream Bedolaga client.
All log output is produced by uvicorn/FastMCP and contains no API key, no base
URL and no tool results.
"""

from __future__ import annotations

import asyncio
import os
from typing import Mapping

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from . import __version__
from .config import load_config
from .server import SERVER_NAME, create_server
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


def create_app() -> Starlette:
    """Build the Starlette app for the sessionful Streamable HTTP transport."""
    server = create_server()

    @server.custom_route("/health", methods=["GET"])
    async def health(request) -> JSONResponse:  # noqa: ARG001 (signature fixed by Starlette)
        return JSONResponse(
            {
                "status": "UP",
                "version": __version__,
                "name": SERVER_NAME,
            }
        )

    return server.streamable_http_app()


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
    app = create_app()
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
