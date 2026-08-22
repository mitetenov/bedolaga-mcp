"""bedolaga_mcp.tools — the single registry of Bedolaga MCP tools.

Both transport entrypoints (stdio in ``bedolaga_server.py`` and Streamable
HTTP in ``http_server.py``) list and register tools exclusively through this
module. No other module owns tool names, descriptions, input schemas or
handlers, so HTTP and stdio can never drift apart.

The tool handlers below are **interim stubs**: they return the unified error
envelope from the spec and are replaced by the real Bedolaga API logic in a
later task. The error message never contains internal URLs, secrets or raw
upstream bodies.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp.utilities.func_metadata import func_metadata
from pydantic import Field

__all__ = ["list_tools", "register_tools", "call_tool", "make_error"]

_SOURCE = "bedolaga-mcp"
_INTERIM_MESSAGE = "Bedolaga Web API integration is not implemented yet"


def make_error(
    tool: str,
    code: str,
    message: str,
    retryable: bool = False,
) -> dict[str, Any]:
    """Build the unified error envelope from the spec."""
    return {
        "ok": False,
        "source": _SOURCE,
        "tool": tool,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }


def bedolaga_user_get(telegram_id: int) -> dict[str, Any]:
    """INTERIM STUB — real implementation lands in a later task."""
    return make_error("bedolaga_user_get", "internal_error", _INTERIM_MESSAGE)


def bedolaga_billing_get(
    telegram_id: int,
    limit: Annotated[int, Field(default=20, ge=1, le=50)] = 20,
) -> dict[str, Any]:
    """INTERIM STUB — real implementation lands in a later task."""
    return make_error("bedolaga_billing_get", "internal_error", _INTERIM_MESSAGE)


def bedolaga_referrals_get(telegram_id: int) -> dict[str, Any]:
    """INTERIM STUB — real implementation lands in a later task."""
    return make_error("bedolaga_referrals_get", "internal_error", _INTERIM_MESSAGE)


_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "bedolaga_user_get",
        "description": (
            "Read-only. Get the current user's Bedolaga account and balance by "
            "Telegram ID. A balance credit (deposit) is NOT a purchase — only a "
            "completed subscription_payment confirms a purchase. This tool does "
            "not know the VPN panel status; panel truth is checked via the "
            "separate Remnawave MCP."
        ),
        "handler": bedolaga_user_get,
    },
    {
        "name": "bedolaga_billing_get",
        "description": (
            "Read-only. One call to see balance, recent financial events and "
            "internal Bedolaga purchase records so a top-up can be told apart "
            "from a purchase. deposit means a balance credit, not a purchase; "
            "only a completed subscription_payment confirms a purchase. The "
            "internal bot-side record status (bot_record_status) is NOT the VPN "
            "panel status — panel truth is checked via the separate Remnawave "
            "MCP."
        ),
        "handler": bedolaga_billing_get,
    },
    {
        "name": "bedolaga_referrals_get",
        "description": (
            "Read-only. Get the current user's referral summary in Bedolaga: "
            "referral code, invitee counts and earnings, without any third-party "
            "personal data. Subscription and VPN panel status are checked via the "
            "separate Remnawave MCP."
        ),
        "handler": bedolaga_referrals_get,
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
    """Return the three public tool definitions for MCP ``tools/list``."""
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

    Arguments are validated with the same pydantic model FastMCP uses.
    Raises :class:`KeyError` for unknown tool names and pydantic
    ``ValidationError`` for invalid arguments; callers decide how to map
    those onto the error envelope.
    """
    tool = _BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    arg_model = func_metadata(tool["handler"]).arg_model
    validated = arg_model.model_validate(arguments or {})
    return tool["handler"](**validated.model_dump())


def register_tools(server: Any) -> None:
    """Register all three tools (name, description, handler) on a FastMCP server."""
    for tool in _TOOLS:
        server.add_tool(
            tool["handler"],
            name=tool["name"],
            description=tool["description"],
        )
