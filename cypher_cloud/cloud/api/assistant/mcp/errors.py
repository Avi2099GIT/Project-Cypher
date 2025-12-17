from __future__ import annotations


class MCPError(Exception):
    """Base class for MCP related errors."""


class MCPConfigError(MCPError):
    """Configuration missing/invalid for a client."""


class MCPConnectionError(MCPError):
    """Connectivity / transport error talking to an MCP backend."""


class MCPToolError(MCPError):
    """Specific tool invocation error (sanitized)."""


class MCPNotAvailableError(MCPError):
    """Raised when an MCP client is currently disabled/unavailable."""
