"""Bedolaga MCP server package.

Exposes eight read-only tools defined and registered in :mod:`bedolaga_mcp.tools`.
The MCP server object is built by :func:`bedolaga_mcp.server.create_server` and
served over sessionful Streamable HTTP (:mod:`bedolaga_mcp.http`) or stdio
(:mod:`bedolaga_mcp.stdio`).

Importing this package has no side effects: no client is created and no tool is
registered until a transport entrypoint starts the server.
"""

__version__ = "1.2.0"

__all__ = ["__version__"]

