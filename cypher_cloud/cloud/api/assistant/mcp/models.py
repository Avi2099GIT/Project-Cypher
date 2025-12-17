from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class MCPToolDescriptor:
    name: str
    description: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None


@dataclass
class MCPCallResult:
    tool: str
    payload: Dict[str, Any]
    success: bool
    error: Optional[str] = None
    raw: Optional[Any] = None
