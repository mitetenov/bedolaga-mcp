"""bedolaga_mcp.tools — the single registry of Bedolaga MCP tools.

Both transport entrypoints (stdio in ``bedolaga_server.py`` and Streamable
HTTP in ``http_server.py``) list and register tools exclusively through this
module. No other module owns tool names, descriptions, input schemas or
handlers, so HTTP and stdio can never drift apart.

The three real read-only handlers live in :mod:`~bedolaga_mcp.tools.user`,
:mod:`~bedolaga_mcp.tools.billing` and :mod:`~bedolaga_mcp.tools.referrals`.
Each handler is an async function whose first argument is the
:class:`~bedolaga_mcp.client.BedolagaClient` (dependency injection, "Option B");
this registry injects the client and maps every domain exception onto the
unified error envelope from :mod:`bedolaga_mcp.contracts` — the tool layer
never composes an error message by hand.

Client lifecycle
----------------
The registry owns the Bedolaga client so the entrypoints stay unchanged. The
client is created **lazily** on the first tool call (importing this module has
no side effects) and can be closed on shutdown via :func:`close_client` (a
later task wires it into the server lifespan):

* **FastMCP / HTTP path** (``register_tools``): handlers receive the shared
  process-lifetime client created by :func:`_get_client`. One connection pool
  serves every request on the server's single event loop.

* **Legacy stdio path** (``call_tool``): the stdio loop is synchronous and runs
  each request inside a fresh ``asyncio.run`` event loop. An ``httpx`` client
  cannot be reused across two ``asyncio.run`` loops (``RuntimeError: Event loop
  is closed``), so ``call_tool`` creates a **fresh client per call** and closes
  it in a ``finally``. This is a deliberate legacy-shim exception; a later task
  migrates stdio onto the same shared client.

Schemas are derived from the registered handler annotations via
``func_metadata`` — the exact derivation FastMCP uses internally — so
``list_tools``, ``call_tool`` and ``register_tools`` always agree on the input
schema.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.fastmcp.utilities.func_metadata import func_metadata
from pydantic import Field

from ..client import BedolagaClient
from ..config import load_config
from ..contracts import make_error_envelope
from ..errors import BedolagaError, IdentityUnavailableError, InternalError

__all__ = [
    "call_tool",
    "close_client",
    "list_tools",
    "register_tools",
]


from .identity import require_internal_id
from . import billing, gifts, payment_status, promocode, referrals, subscription, tickets, user



def error_envelope(exc: BaseException, tool: str) -> dict[str, Any]:
    """Map one exception to the unified error envelope from the spec.

    Domain exceptions keep their fixed ``code`` and catalog ``retryable`` flag
    plus a safe ``exc.message``; ``exc.detail`` (a bounded upstream snippet) is
    never shown to the model. Unexpected exceptions become a non-retryable
    ``internal_error`` with a generic message.
    """
    if isinstance(exc, BedolagaError):
        return make_error_envelope(tool, exc.code, exc.message, exc.retryable)
    return make_error_envelope(tool, "internal_error", "Internal error")


async def _run(
    impl: Callable[..., Any],
    client_provider: Callable[[], BedolagaClient],
    tool_name: str,
    arguments: dict[str, Any],
    *,
    close: bool = False,
) -> dict[str, Any]:
    """Run one real handler with an injected client, mapping errors to envelopes."""
    client: BedolagaClient | None = None
    try:
        client = client_provider()
        return await impl(client, **arguments)
    except BedolagaError as exc:
        return error_envelope(exc, tool_name)
    except Exception:  # noqa: BLE001 - sanitize every unexpected MCP boundary failure
        return error_envelope(InternalError("Internal error"), tool_name)
    finally:
        if close and client is not None:
            await client.aclose()


# --- Client lifecycle -------------------------------------------------------

_client_state: dict[str, BedolagaClient] = {}


def _make_client() -> BedolagaClient:
    """Create a client from the current environment configuration."""
    return BedolagaClient(load_config())


def _get_client() -> BedolagaClient:
    """Lazily create and return the shared process-lifetime client."""
    client = _client_state.get("client")
    if client is None:
        client = _make_client()
        _client_state["client"] = client
    return client


async def close_client() -> None:
    """Close the shared client if it was created (safe to call any time)."""
    client = _client_state.pop("client", None)
    if client is not None:
        await client.aclose()


# --- Public wrappers (clean annotations define the input schemas) ----------


async def _user_get_handler(
    telegram_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    return await _run(
        user.bedolaga_user_get,
        _get_client,
        "bedolaga_user_get",
        {"telegram_id": telegram_id, "user_id": user_id},
    )


async def _billing_get_handler(
    telegram_id: int | None = None,
    user_id: int | None = None,
    limit: Annotated[int, Field(default=20, ge=1, le=50)] = 20,
) -> dict[str, Any]:
    return await _run(
        billing.bedolaga_billing_get,
        _get_client,
        "bedolaga_billing_get",
        {"telegram_id": telegram_id, "user_id": user_id, "limit": limit},
    )


async def _referrals_get_handler(
    telegram_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    return await _run(
        referrals.bedolaga_referrals_get,
        _get_client,
        "bedolaga_referrals_get",
        {"telegram_id": telegram_id, "user_id": user_id},
    )


async def _subscription_get_handler(
    telegram_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    return await _run(
        subscription.bedolaga_subscription_get,
        _get_client,
        "bedolaga_subscription_get",
        {"telegram_id": telegram_id, "user_id": user_id},
    )


async def _tickets_get_handler(
    telegram_id: int | None = None,
    user_id: int | None = None,
    limit: Annotated[int, Field(default=10, ge=1, le=50)] = 10,
) -> dict[str, Any]:
    return await _run(
        tickets.bedolaga_tickets_get,
        _get_client,
        "bedolaga_tickets_get",
        {"telegram_id": telegram_id, "user_id": user_id, "limit": limit},
    )


async def _payment_status_get_handler(
    telegram_id: int | None = None,
    user_id: int | None = None,
    limit: Annotated[int, Field(default=5, ge=1, le=20)] = 5,
) -> dict[str, Any]:
    return await _run(
        payment_status.bedolaga_payment_status_get,
        _get_client,
        "bedolaga_payment_status_get",
        {"telegram_id": telegram_id, "user_id": user_id, "limit": limit},
    )


async def _promocode_check_handler(
    code: Annotated[str, Field(min_length=1)],
    telegram_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    return await _run(
        promocode.bedolaga_promocode_check,
        _get_client,
        "bedolaga_promocode_check",
        {"telegram_id": telegram_id, "user_id": user_id, "code": code},
    )


async def _gifts_get_handler(
    telegram_id: int | None = None,
    user_id: int | None = None,
    limit: Annotated[int, Field(default=20, ge=1, le=50)] = 20,
) -> dict[str, Any]:
    return await _run(
        gifts.bedolaga_gifts_get,
        _get_client,
        "bedolaga_gifts_get",
        {"telegram_id": telegram_id, "user_id": user_id, "limit": limit},
    )


_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "bedolaga_user_get",
        "description": (
            "Read-only. Get the current user's Bedolaga account and balance. "
            "Identity is pinned by the system, never by the caller: provide "
            "exactly one of telegram_id (positive Telegram ID) or user_id "
            "(internal Bedolaga id for email-only cabinet tickets). A balance "
            "credit (deposit) is NOT a purchase — only a completed "
            "subscription_payment confirms a purchase. This tool does not know "
            "the VPN panel status; panel truth is checked via the separate "
            "Remnawave MCP."
        ),
        "handler": _user_get_handler,
        "impl": user.bedolaga_user_get,
    },
    {
        "name": "bedolaga_billing_get",
        "description": (
            "Read-only. One call to see balance, recent financial events and "
            "internal Bedolaga purchase records so a top-up can be told apart "
            "from a purchase. Identity is pinned by the system, never by the "
            "caller: provide exactly one of telegram_id (positive Telegram ID) "
            "or user_id (internal Bedolaga id for email-only cabinet tickets). "
            "deposit means a balance credit, not a purchase; only a completed "
            "subscription_payment confirms a purchase. The internal bot-side "
            "record status (bot_record_status) is NOT the VPN panel status — "
            "panel truth is checked via the separate Remnawave MCP."
        ),
        "handler": _billing_get_handler,
        "impl": billing.bedolaga_billing_get,
    },
    {
        "name": "bedolaga_referrals_get",
        "description": (
            "Read-only. Get the current user's referral summary in Bedolaga: "
            "referral code, invitee counts and earnings, without any "
            "third-party personal data. Identity is pinned by the system, never "
            "by the caller: provide exactly one of telegram_id (positive "
            "Telegram ID) or user_id (internal Bedolaga id for email-only "
            "cabinet tickets). Subscription and VPN panel status are checked "
            "via the separate Remnawave MCP."
        ),
        "handler": _referrals_get_handler,
        "impl": referrals.bedolaga_referrals_get,
    },
    {
        "name": "bedolaga_subscription_get",
        "description": (
            "Read-only. Get the current user's bot-side subscription records and "
            "lifecycle dates (created_at, start_date, end_date, trial, autopay). "
            "Identity is pinned by the system, never by the caller: provide "
            "exactly one of telegram_id (positive Telegram ID) or user_id "
            "(internal Bedolaga id for email-only cabinet tickets). This record "
            "reflects bot-side purchases only and is NOT the VPN panel status; "
            "verify actual panel state via Remnawave MCP."
        ),
        "handler": _subscription_get_handler,
        "impl": subscription.bedolaga_subscription_get,
    },
    {
        "name": "bedolaga_tickets_get",
        "description": (
            "Read-only. Get the current user's support ticket summaries (id, title, "
            "status, priority, timestamps) without message contents or media. "
            "Identity is pinned by the system, never by the caller: provide "
            "exactly one of telegram_id (positive Telegram ID) or user_id "
            "(internal Bedolaga id for email-only cabinet tickets)."
        ),
        "handler": _tickets_get_handler,
        "impl": tickets.bedolaga_tickets_get,
    },
    {
        "name": "bedolaga_payment_status_get",
        "description": (
            "Read-only. Get the current user's accounting payment events and "
            "completion status (completed / not_completed / unknown). Identity "
            "is pinned by the system, never by the caller: provide exactly one "
            "of telegram_id (positive Telegram ID) or user_id (internal Bedolaga "
            "id for email-only cabinet tickets). not_completed indicates only "
            "that the payment is not completed in bot accounting, NOT that a "
            "provider attempt failed or is pending."
        ),
        "handler": _payment_status_get_handler,
        "impl": payment_status.bedolaga_payment_status_get,
    },
    {
        "name": "bedolaga_promocode_check",
        "description": (
            "Read-only. Check global promo code definition, validity, bonus "
            "amounts, and remaining uses. Identity is pinned by the system, "
            "never by the caller: provide exactly one of telegram_id (positive "
            "Telegram ID) or user_id (internal Bedolaga id for email-only "
            "cabinet tickets). Checks global definition only; cannot verify if "
            "the current user is eligible or has already redeemed the code."
        ),
        "handler": _promocode_check_handler,
        "impl": promocode.bedolaga_promocode_check,
    },
    {
        "name": "bedolaga_gifts_get",
        "description": (
            "Read-only. Get the current user's gift purchase accounting events. "
            "Identity is pinned by the system, never by the caller: provide "
            "exactly one of telegram_id (positive Telegram ID) or user_id "
            "(internal Bedolaga id for email-only cabinet tickets). Shows own "
            "gift purchase transactions only; received gifts, gift tokens, and "
            "recipient activation status are not available."
        ),
        "handler": _gifts_get_handler,
        "impl": gifts.bedolaga_gifts_get,
    },
)

_BY_NAME: dict[str, dict[str, Any]] = {tool["name"]: tool for tool in _TOOLS}


def _input_schema(handler: Any) -> dict[str, Any]:
    """Derive the JSON Schema from the handler annotations.

    Uses the same derivation FastMCP uses internally, so the schema reported
    by :func:`list_tools` and the schema FastMCP generates are identical.
    """
    return func_metadata(handler).arg_model.model_json_schema()


def list_tools() -> list[dict[str, Any]]:
    """Return the eight public tool definitions for MCP ``tools/list``."""
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": _input_schema(tool["handler"]),
        }
        for tool in _TOOLS
    ]


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Dispatch a ``tools/call`` through the registry handler.

    Arguments are validated with the same pydantic model FastMCP uses, then the
    real handler runs on a fresh per-call client (see the module docstring).
    Raises :class:`KeyError` for unknown tool names and pydantic
    ``ValidationError`` for invalid arguments; callers decide how to map those
    onto the error envelope.
    """
    tool = _BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    arg_model = func_metadata(tool["handler"]).arg_model
    validated = arg_model.model_validate(arguments or {})
    return asyncio.run(
        _run(
            tool["impl"],
            _make_client,
            tool["name"],
            validated.model_dump(),
            close=True,
        )
    )


def register_tools(server: Any) -> None:
    """Register all eight tools (name, description, handler) on a FastMCP server."""
    for tool in _TOOLS:
        server.add_tool(
            tool["handler"],
            name=tool["name"],
            description=tool["description"],
        )

