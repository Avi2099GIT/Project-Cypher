from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time
import threading
import logging
import uuid

from .node import NodeStatus  # you already have this Enum in node.py

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# DATA MODEL
# ---------------------------------------------------------

@dataclass
class GraphEvent:
    trace_id: str
    timestamp: float
    node: str
    status: str
    message: str
    extra: Dict[str, Any]


# ---------------------------------------------------------
# TRACER CORE
# ---------------------------------------------------------

class GraphTracer:
    """
    Singleton in-memory execution tracer.

    REQUIRED by:
      - cypher_graph.py
      - executor.py
      - failure_node.py
      - React Trace Inspector
      - /debug/plan (via context attachment)
    """

    def __init__(self) -> None:
        self._events: List[GraphEvent] = []
        self._lock = threading.Lock()
        # trace_id -> orchestration context (ctx dict)
        self._contexts: Dict[str, Dict[str, Any]] = {}
        self._current_trace_id: Optional[str] = None

    # -------------------------
    # TRACE ID MANAGEMENT
    # -------------------------

    def new_trace(self) -> str:
        """
        Create and remember a new trace id for the next run.
        """
        tid = str(uuid.uuid4())
        with self._lock:
            self._current_trace_id = tid
        return tid

    @property
    def current_trace_id(self) -> Optional[str]:
        with self._lock:
            return self._current_trace_id

    # -------------------------
    # CONTEXT ATTACHMENT
    # -------------------------

    def attach_context(self, trace_id: str, ctx: Dict[str, Any]) -> None:
        """
        Attach the *orchestration context* (the ctx dict you pass
        through the graph) to a given trace_id so /debug/plan can inspect it.
        """
        with self._lock:
            self._contexts[trace_id] = ctx

    def get_context(self, trace_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._contexts.get(trace_id)

    def last_context(self) -> Optional[Dict[str, Any]]:
        """
        Convenience helper: get the context for the most recent trace
        (by event order).
        """
        with self._lock:
            if not self._events:
                return None
            last_id = self._events[-1].trace_id
            return self._contexts.get(last_id)

    # -------------------------
    # RECORD EVENTS
    # -------------------------

    def record(
        self,
        *,
        trace_id: str,
        node: str,
        status: NodeStatus | str,
        message: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a single node event.
        """
        evt = GraphEvent(
            trace_id=trace_id,
            timestamp=time.time(),
            node=node,
            status=status.name if hasattr(status, "name") else str(status),
            message=message,
            extra=extra or {},
        )

        with self._lock:
            self._events.append(evt)

        logger.debug("TRACE %s | %s | %s", evt.node, evt.status, evt.message)

    # -------------------------
    # ACCESSORS
    # -------------------------

    @property
    def events(self) -> List[GraphEvent]:
        with self._lock:
            return list(self._events)

    def to_dict(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "trace_id": e.trace_id,
                    "timestamp": e.timestamp,
                    "node": e.node,
                    "status": e.status,
                    "message": e.message,
                    "extra": e.extra,
                }
                for e in self._events
            ]

    def clear(self) -> None:
        """
        Clear recorded events for a fresh run.

        NOTE: we do NOT clear _contexts here so that /debug/plan
        can still inspect previous runs if needed.
        """
        with self._lock:
            self._events.clear()

    # -------------------------
    # UI SUPPORT METHODS
    # -------------------------

    def timeline(self) -> List[Dict[str, Any]]:
        """Events ordered by time (for UI replay)."""
        return sorted(self.to_dict(), key=lambda e: e["timestamp"])

    def slowest_nodes(self, top: int = 5) -> List[Dict[str, Any]]:
        """
        Aggregates total duration per node across all traces.
        Used by the top-level /debug/trace slowest section.
        """
        durations: Dict[str, float] = {}
        counts: Dict[str, int] = {}

        with self._lock:
            for e in self._events:
                ms = e.extra.get("duration_ms")
                if ms is None:
                    continue
                try:
                    ms_val = float(ms)
                except Exception:
                    continue
                durations[e.node] = durations.get(e.node, 0.0) + ms_val
                counts[e.node] = counts.get(e.node, 0) + 1

        slow = []
        for node, total in durations.items():
            count = counts.get(node, 1)
            slow.append(
                {
                    "node": node,
                    "total_ms": total,
                    "count": count,
                    "avg": total / max(count, 1),
                }
            )

        return sorted(slow, key=lambda x: x["total_ms"], reverse=True)[:top]

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._events)
            per_node: Dict[str, int] = {}
            failures = 0

            for e in self._events:
                per_node[e.node] = per_node.get(e.node, 0) + 1
                if e.status in ("FAILED", "ERROR"):
                    failures += 1

            return {
                "total_events": total,
                "per_node": per_node,
                "failures": failures,
            }

    # -------- extra helpers used by router endpoints --------

    def heatmap(self) -> Dict[str, Any]:
        """
        Structure events as trace → node grid. Good for raw debugging.
        """
        with self._lock:
            events = list(self._events)

        traces: Dict[str, Dict[str, Any]] = {}
        for e in events:
            t = traces.setdefault(e.trace_id, {})
            t[e.node] = {
                "status": e.status,
                "message": e.message,
                "duration_ms": e.extra.get("duration_ms"),
            }

        return {"traces": traces}

    def slow_nodes(self) -> List[Dict[str, Any]]:
        """
        Same as slowest_nodes but returns full list (for /debug/trace/slow).
        """
        with self._lock:
            events = list(self._events)

        durations: Dict[str, float] = {}
        counts: Dict[str, int] = {}

        for e in events:
            ms = e.extra.get("duration_ms")
            if ms is None:
                continue
            try:
                ms_val = float(ms)
            except Exception:
                continue
            durations[e.node] = durations.get(e.node, 0.0) + ms_val
            counts[e.node] = counts.get(e.node, 0) + 1

        nodes = []
        for node, total in durations.items():
            count = counts.get(node, 1)
            nodes.append(
                {
                    "node": node,
                    "total_ms": total,
                    "count": count,
                    "avg": total / max(count, 1),
                }
            )

        return sorted(nodes, key=lambda x: x["total_ms"], reverse=True)

    def failure_map(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Map of trace_id → list of failed node events.
        """
        with self._lock:
            events = list(self._events)

        out: Dict[str, List[Dict[str, Any]]] = {}
        for e in events:
            if e.status not in ("FAILED", "ERROR"):
                continue
            out.setdefault(e.trace_id, []).append(
                {
                    "node": e.node,
                    "message": e.message,
                    "extra": e.extra,
                }
            )
        return out

    def trace_by_id(self, trace_id: str) -> List[Dict[str, Any]]:
        """
        Return all events for a specific trace id.
        """
        return [e for e in self.to_dict() if e["trace_id"] == trace_id]


# ---------------------------------------------------------
# GLOBAL SINGLETON (DO NOT DELETE)
# ---------------------------------------------------------

tracer = GraphTracer()
