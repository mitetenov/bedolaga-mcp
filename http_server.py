"""Thin compatibility launcher for the Streamable HTTP transport.

Starts the sessionful Streamable HTTP server on ``/`` (same lifecycle as the
mcp-remnawave server supportBot already uses). All server logic lives in
:mod:`bedolaga_mcp`; this file exists so existing Docker/desktop commands that
run ``python3 http_server.py`` keep working. Configuration is read from the
environment via :func:`bedolaga_mcp.config.load_config`.
"""

from bedolaga_mcp.http import run

if __name__ == "__main__":
    run()
