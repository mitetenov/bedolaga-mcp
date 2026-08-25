"""The shared upstream ``httpx`` client must close exactly once, on every exit
path: HTTP shutdown, stdio EOF, and a stdio SIGTERM/SIGINT.

Two things are tested separately, deliberately:

1. ``close_client()`` itself is idempotent (popping the client out of
   ``_client_state`` before closing it), so calling it more than once from
   different shutdown hooks can never double-``aclose()`` the real client.
2. Each transport's shutdown hook (``_BedolagaHTTPServer._serve``'s
   ``finally``, and stdio's normal-EOF ``finally`` / signal-triggered
   ``_shutdown()``) actually calls :func:`bedolaga_mcp.tools.close_client` on
   every exit path, including when the server coroutine raises.
"""

from __future__ import annotations

import asyncio
import signal
import unittest
from unittest.mock import AsyncMock, patch

import uvicorn

import bedolaga_mcp.stdio as stdio
import bedolaga_mcp.tools as tools


class CloseClientIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_client_only_ever_acloses_once(self) -> None:
        fake_client = AsyncMock()
        tools._client_state["client"] = fake_client
        try:
            await tools.close_client()
            await tools.close_client()  # a second call must be a no-op
        finally:
            tools._client_state.pop("client", None)

        fake_client.aclose.assert_awaited_once()

    async def test_close_client_is_safe_when_no_client_was_ever_created(self) -> None:
        tools._client_state.pop("client", None)
        await tools.close_client()  # must not raise


class HttpShutdownClosesClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_shutdown_closes_the_shared_client_once(self) -> None:
        from bedolaga_mcp.http import _BedolagaHTTPServer

        server = _BedolagaHTTPServer(uvicorn.Config(app=lambda *a, **k: None, host="127.0.0.1", port=0))
        with (
            patch.object(uvicorn.Server, "_serve", new=AsyncMock(return_value=None)) as base_serve,
            patch("bedolaga_mcp.http.close_client", new=AsyncMock()) as mock_close,
        ):
            await server._serve()

        base_serve.assert_awaited_once()
        mock_close.assert_awaited_once()

    async def test_shutdown_after_a_crash_still_closes_the_shared_client(self) -> None:
        from bedolaga_mcp.http import _BedolagaHTTPServer

        server = _BedolagaHTTPServer(uvicorn.Config(app=lambda *a, **k: None, host="127.0.0.1", port=0))
        with (
            patch.object(uvicorn.Server, "_serve", new=AsyncMock(side_effect=RuntimeError("boom"))),
            patch("bedolaga_mcp.http.close_client", new=AsyncMock()) as mock_close,
        ):
            with self.assertRaises(RuntimeError):
                await server._serve()

        mock_close.assert_awaited_once()


class _FakeServer:
    """Stand-in for the real ``MCPServer`` used only to drive ``run_stdio_async``."""

    def __init__(self, run_stdio_async) -> None:
        self.run_stdio_async = run_stdio_async


class StdioEofClosesClientTests(unittest.TestCase):
    def test_eof_completion_closes_the_shared_client_exactly_once(self) -> None:
        async def eof_immediately() -> None:
            return None  # the parent closed stdin; run_stdio_async just returns

        with (
            patch.object(stdio, "create_server", return_value=_FakeServer(eof_immediately)),
            patch.object(stdio, "close_client", new=AsyncMock()) as mock_close,
        ):
            stdio._run_stdio()

        mock_close.assert_awaited_once()


class StdioSignalClosesClientTests(unittest.TestCase):
    """Drives the real signal-handler registration and the real ``_shutdown``
    closure in :func:`bedolaga_mcp.stdio._run_stdio`, without sending an actual
    OS signal (which would hit this test process's own default disposition)
    and without ever calling the real ``os._exit`` (which would kill the test
    run outright)."""

    def test_sigterm_closes_the_shared_client_and_requests_process_exit(self) -> None:
        probe_loop = asyncio.new_event_loop()
        loop_class = type(probe_loop)
        probe_loop.close()
        captured_handlers: dict[int, object] = {}

        def fake_add_signal_handler(self, sig, callback, *args):
            captured_handlers[sig] = callback

        async def blocks_until_signaled() -> None:
            # Mirrors run_stdio_async(): blocks until shutdown intervenes. The
            # captured SIGTERM handler is invoked here, on the loop, exactly
            # as the OS would invoke it once a real signal arrived.
            stop = asyncio.Event()
            captured_handlers[signal.SIGTERM]()
            # os._exit is mocked below to set this same stop-event instead of
            # actually terminating the process, so the coroutine can return.
            asyncio.get_event_loop()._test_stop_event = stop  # type: ignore[attr-defined]
            await stop.wait()

        def fake_os_exit(code: int) -> None:
            fake_os_exit.calls.append(code)
            loop = asyncio.get_event_loop()
            getattr(loop, "_test_stop_event").set()

        fake_os_exit.calls = []

        with (
            patch.object(loop_class, "add_signal_handler", fake_add_signal_handler),
            patch.object(stdio, "create_server", return_value=_FakeServer(blocks_until_signaled)),
            patch.object(stdio, "close_client", new=AsyncMock()) as mock_close,
            patch.object(stdio.os, "_exit", fake_os_exit),
        ):
            stdio._run_stdio()

        self.assertEqual(fake_os_exit.calls, [0])
        self.assertGreaterEqual(mock_close.await_count, 1)


if __name__ == "__main__":
    unittest.main()
