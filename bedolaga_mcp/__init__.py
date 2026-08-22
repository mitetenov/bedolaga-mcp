"""Bedolaga MCP server package.

Exposes exactly three read-only tools — ``bedolaga_user_get``,
``bedolaga_billing_get`` and ``bedolaga_referrals_get`` — defined and
registered in :mod:`bedolaga_mcp.tools`. Importing this package has no side
effects.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
