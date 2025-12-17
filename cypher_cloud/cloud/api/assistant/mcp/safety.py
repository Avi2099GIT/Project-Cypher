from __future__ import annotations

import os
import re

from .errors import MCPToolError

FORBIDDEN_SHELL_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"shutdown",
    r"reboot",
    r"mkfs",
    r"format\s+c:",
]


def is_dry_run() -> bool:
    return os.getenv("MCP_DRY_RUN", "false").lower() in ("1", "true", "yes")


def validate_shell_command(cmd: str) -> None:
    if not isinstance(cmd, str) or not cmd.strip():
        raise MCPToolError("Shell command must be a non-empty string")

    lowered = cmd.lower()
    for pat in FORBIDDEN_SHELL_PATTERNS:
        if re.search(pat, lowered):
            raise MCPToolError(f"Blocked dangerous shell command: {cmd}")
