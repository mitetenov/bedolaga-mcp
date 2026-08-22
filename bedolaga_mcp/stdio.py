"""stdio transport for the Bedolaga MCP server.

Runs the MCP SDK stdio handshake on the SAME server factory and tool registry as
the HTTP transport, so both transports expose identical tools and schemas. The
old hand-rolled JSON-line loop that only understood ``tools/list`` and
``tools/call`` is removed.

Lifecycle:

* Normal shutdown is the parent closing stdin (EOF): ``run_stdio_async``
  returns, the shared upstream Bedolaga client is closed and the process exits.
* On SIGTERM/SIGINT the shared client is closed and the process exits cleanly.
  The OS-level stdio reader thread may still be blocked on a pipe read (anyio
  cannot interrupt a blocking ``read(0)`` on macOS), so instead of waiting on
  that thread we close the client and exit with code 0.
"""

from __future__ import annotations

import asyncio
import os
import signal

from .server import create_server
from .tools import close_client


def _run_stdio() -> None:
    server = create_server()

    async def _serve() -> None:
        await server.run_stdio_async()

    async def _shutdown() -> None:
        await close_client()
        os._exit(0)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        main_task = loop.create_task(_serve())
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: loop.create_task(_shutdown()))
            except (NotImplementedError, RuntimeError):
                pass
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        pass
    finally:
        # Normal EOF path: the serve task completed; close the shared client.
        loop.run_until_complete(close_client())
        loop.close()
        asyncio.set_event_loop(None)


def run() -> None:
    """Run the stdio transport until the parent closes stdin or a signal arrives."""
    _run_stdio()


__all__ = ["run"]


if __name__ == "__main__":
    run()
