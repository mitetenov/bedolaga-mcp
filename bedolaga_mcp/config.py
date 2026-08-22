"""Process-lifetime configuration for the Bedolaga MCP server.

Configuration is loaded once at startup and validated eagerly so a
misconfigured process fails fast instead of failing at request time. The
Bedolaga base URL is normalized (trailing ``/`` stripped) in exactly this one
place; nothing else in the package composes URLs by string concatenation.
The API key is never logged or printed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from .errors import NotConfiguredError

DEFAULT_TIMEOUT_MS = 10000


@dataclass(frozen=True)
class Config:
    """Parsed and validated environment configuration."""

    api_url: str
    api_key: str
    timeout_ms: int
    mcp_http_host: str
    mcp_http_port: int

    @property
    def timeout_seconds(self) -> float:
        """Timeout in seconds for httpx, derived once from ``timeout_ms``."""
        return self.timeout_ms / 1000.0


def _require_non_empty(environ: Mapping[str, str], name: str, purpose: str) -> str:
    value = (environ.get(name) or "").strip()
    if not value:
        raise NotConfiguredError(f"{name} is required ({purpose})")
    return value


def _require_http_url(value: str) -> str:
    """Validate and normalize an http(s) base URL without network I/O."""
    if "://" not in value:
        raise NotConfiguredError("BEDOLAGA_API_URL must be an http(s) URL")
    scheme, _, rest = value.partition("://")
    if scheme.lower() not in ("http", "https") or not rest.strip():
        raise NotConfiguredError("BEDOLAGA_API_URL must be an http(s) URL")
    return value.rstrip("/")


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    """Load and validate configuration from the environment.

    Pass ``environ`` to inject a mapping for tests or manual smoke checks;
    defaults to :data:`os.environ`.
    """
    env = os.environ if environ is None else environ

    api_url = _require_non_empty(env, "BEDOLAGA_API_URL", "Bedolaga Web API base URL")
    api_url = _require_http_url(api_url)

    api_key = _require_non_empty(env, "BEDOLAGA_API_KEY", "Bedolaga Web API key")

    timeout_raw = (env.get("BEDOLAGA_TIMEOUT_MS") or "").strip() or str(DEFAULT_TIMEOUT_MS)
    try:
        timeout_ms = int(timeout_raw)
    except ValueError:
        raise NotConfiguredError(
            "BEDOLAGA_TIMEOUT_MS must be a positive integer (milliseconds)"
        ) from None
    if timeout_ms <= 0:
        raise NotConfiguredError(
            "BEDOLAGA_TIMEOUT_MS must be a positive integer (milliseconds)"
        )

    mcp_http_host = _require_non_empty(env, "MCP_HTTP_HOST", "HTTP bind host")

    port_raw = _require_non_empty(env, "MCP_HTTP_PORT", "HTTP bind port")
    try:
        mcp_http_port = int(port_raw)
    except ValueError:
        raise NotConfiguredError("MCP_HTTP_PORT must be an integer between 1 and 65535") from None
    if not 1 <= mcp_http_port <= 65535:
        raise NotConfiguredError("MCP_HTTP_PORT must be an integer between 1 and 65535")

    return Config(
        api_url=api_url,
        api_key=api_key,
        timeout_ms=timeout_ms,
        mcp_http_host=mcp_http_host,
        mcp_http_port=mcp_http_port,
    )


__all__ = ["Config", "DEFAULT_TIMEOUT_MS", "load_config"]
