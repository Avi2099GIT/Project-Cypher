from __future__ import annotations
from typing import Any, Dict
import threading
import time

_lock = threading.Lock()
mcp_metrics: Dict[str, Any] = {"clients": {}, "last_updated": None}


def record_call(client: str, tool: str, duration_ms: float, success: bool, error: str | None = None) -> None:
    now = time.time()
    with _lock:
        client_stats = mcp_metrics["clients"].setdefault(client, {"total_calls": 0, "total_failures": 0, "tools": {}})
        client_stats["total_calls"] += 1
        if not success:
            client_stats["total_failures"] += 1

        tool_stats = client_stats["tools"].setdefault(tool, {"calls": 0, "failures": 0, "avg_ms": 0.0, "last_error": None})
        tool_stats["calls"] += 1
        if not success:
            tool_stats["failures"] += 1
            tool_stats["last_error"] = error

        prev_avg = tool_stats["avg_ms"]
        n = tool_stats["calls"]
        tool_stats["avg_ms"] = ((prev_avg * (n - 1)) + duration_ms) / max(n, 1)

        mcp_metrics["last_updated"] = now


def snapshot_metrics() -> Dict[str, Any]:
    with _lock:
        return {"clients": {k: dict(v) for k, v in mcp_metrics["clients"].items()}, "last_updated": mcp_metrics["last_updated"]}
