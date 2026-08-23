"""Domain error types and the fixed spec error-code mapping for Bedolaga MCP.

Every failure produced by the client (and later by the tool layer) maps onto
one of the ten fixed error codes from the specification, each with an
unambiguous ``retryable`` flag. Technical messages never contain the API key,
the full upstream response body or the base URL with secrets.
"""

from __future__ import annotations

from typing import Final

MAX_BODY_IN_EXCEPTION: Final = 200


def bounded_body(body: str | None) -> str | None:
    """Return a small bounded prefix of an upstream body for diagnostics."""
    if not body:
        return None
    text = body.strip()
    if len(text) > MAX_BODY_IN_EXCEPTION:
        text = text[:MAX_BODY_IN_EXCEPTION] + "\u2026"
    return text


class BedolagaError(Exception):
    """Base class for all Bedolaga client errors.

    Subclasses declare a fixed ``code`` (one of the ten spec error codes) and
    an unambiguous ``retryable`` flag. ``detail`` is optional and only ever
    holds a bounded, non-secret diagnostic value (see :func:`bounded_body`).
    """

    code: str = "internal_error"
    retryable: bool = False

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class InvalidInputError(BedolagaError):
    """Client-side bad input, e.g. a non-positive telegram_id."""

    code = "invalid_input"
    retryable = False


class NotConfiguredError(BedolagaError):
    """Required environment configuration is missing or invalid."""

    code = "not_configured"
    retryable = False


class IdentityUnavailableError(BedolagaError):
    """The caller's identity cannot be resolved to a Bedolaga user."""

    code = "identity_unavailable"
    retryable = False


class UserNotFoundError(BedolagaError):
    """Upstream 404: the requested user does not exist."""

    code = "user_not_found"
    retryable = False


class UnauthorizedError(BedolagaError):
    """Upstream 401/403: bad or missing API credentials."""

    code = "unauthorized"
    retryable = False


class RateLimitedError(BedolagaError):
    """Upstream 429: rate limit reached."""

    code = "rate_limited"
    retryable = True


class UpstreamTimeoutError(BedolagaError):
    """Request timed out or the network failed before a response."""

    code = "upstream_timeout"
    retryable = True


class UpstreamUnavailableError(BedolagaError):
    """Upstream 5xx or an otherwise unrecoverable upstream failure."""

    code = "upstream_unavailable"
    retryable = True


class InvalidUpstreamResponseError(BedolagaError):
    """Upstream returned a body that is not valid JSON or not a JSON object."""

    code = "invalid_upstream_response"
    retryable = False


class InternalError(BedolagaError):
    """Unexpected internal failure that has no more specific mapping."""

    code = "internal_error"
    retryable = False


_SPEC_EXCEPTIONS: tuple[type[BedolagaError], ...] = (
    InvalidInputError,
    NotConfiguredError,
    IdentityUnavailableError,
    UserNotFoundError,
    UnauthorizedError,
    RateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    InvalidUpstreamResponseError,
    InternalError,
)

#: The authoritative table of the ten fixed spec error codes and their
#: retryable flags. Derived from the exception classes so it can never drift.
SPEC_ERROR_CODES: dict[str, bool] = {
    cls.code: cls.retryable for cls in _SPEC_EXCEPTIONS
}

#: Stable mapping from spec error code to its exception class.
BY_CODE: dict[str, type[BedolagaError]] = {
    cls.code: cls for cls in _SPEC_EXCEPTIONS
}


def make_error(code: str, message: str, *, detail: str | None = None) -> BedolagaError:
    """Instantiate the exception registered for ``code``.

    Raises :class:`KeyError` for an unknown code.
    """
    cls = BY_CODE[code]
    return cls(message, detail=detail)


__all__ = [
    "BY_CODE",
    "MAX_BODY_IN_EXCEPTION",
    "SPEC_ERROR_CODES",
    "BedolagaError",
    "IdentityUnavailableError",
    "InternalError",
    "InvalidInputError",
    "InvalidUpstreamResponseError",
    "NotConfiguredError",
    "RateLimitedError",
    "UnauthorizedError",
    "UpstreamTimeoutError",
    "UpstreamUnavailableError",
    "UserNotFoundError",
    "bounded_body",
    "make_error",
]
