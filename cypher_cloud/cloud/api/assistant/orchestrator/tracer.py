from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time
import threading
import logging
import uuid

from .node import NodeStatus

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

    Used by:
      - cypher_graph.py
      - graph.py
      - executor / planner / failure nodes
      - React Trace Inspector (Phase 4 UI)

    Responsibilities:
      • per-node event logging
      • basic performance stats (slow nodes)
      • trace timeline view
      • failure map
      • context attachment (for /debug/plan)
      • trace annotations (EPIC #1)
    """

    def __init__(self) -> None:
        self._events: List[GraphEvent] = []
        self._lock = threading.Lock()

        # execution context & annotations keyed by trace_id
        self._contexts: Dict[str, Any] = {}
        self._annotations: Dict[str, Dict[str, Any]] = {}

    # -------------------------
    # TRACE ID
    # -------------------------

    def new_trace(self) -> str:
        """
        Generate a fresh trace_id for a new end-to-end request.
        Does NOT clear previous events (we keep history).
        """
        return str(uuid.uuid4())

    # -------------------------
    # RECORD EVENTS
    # -------------------------

    def record(
        self,
        *,
        trace_id: str,
        node: str,
        status: NodeStatus,
        message: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
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
        with self._lock:
            self._events.clear()
            self._contexts.clear()
            self._annotations.clear()

    # -------------------------
    # UI SUPPORT METHODS
    # -------------------------

    def timeline(self) -> List[Dict[str, Any]]:
        """Events ordered by time (for UI replay)."""
        return sorted(self.to_dict(), key=lambda e: e["timestamp"])

    def slowest_nodes(self, top: int = 5) -> List[Dict[str, Any]]:
        """
        Nodes with highest cumulative runtime based on extra['duration_ms'].
        """
        durations: Dict[str, float] = {}
        counts: Dict[str, int] = {}

        with self._lock:
            for e in self._events:
                if e.status != "SUCCESS":
                    continue
                ms = float(e.extra.get("duration_ms") or 0)
                if ms <= 0:
                    continue
                durations[e.node] = durations.get(e.node, 0.0) + ms
                counts[e.node] = counts.get(e.node, 0) + 1

        rows: List[Dict[str, Any]] = []
        for node, total in durations.items():
            count = counts.get(node, 1)
            rows.append(
                {
                    "node": node,
                    "total_ms": total,
                    "count": count,
                    "avg": total / count,
                }
            )

        rows.sort(key=lambda r: r["total_ms"], reverse=True)
        return rows[:top]

    # Alias used by router (`/debug/trace/slow`)
    def slow_nodes(self, top: int = 5) -> List[Dict[str, Any]]:
        return self.slowest_nodes(top=top)

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

    # -------------------------
    # CONTEXT + ANNOTATIONS
    # -------------------------

    def attach_context(self, trace_id: str, ctx: Any) -> None:
        """
        Attach the final ExecutionContext (or ctx dict) for a trace.

        Also snapshots any trace annotations present on the context.
        """
        with self._lock:
            self._contexts[trace_id] = ctx

            # Harvest annotations from either attribute or dict key
            annotations: Optional[Dict[str, Any]] = None

            if hasattr(ctx, "trace_annotations"):
                annotations = getattr(ctx, "trace_annotations", None)
            elif isinstance(ctx, dict):
                annotations = ctx.get("trace_annotations")

            if isinstance(annotations, dict):
                # Filter out keys whose value is None, so we don't emit
                # `"arbiter": null` etc. when they were never set.
                clean = {k: v for k, v in annotations.items() if v is not None}
                if clean:
                    self._annotations[trace_id] = clean

    def get_context(self, trace_id: str) -> Any:
        with self._lock:
            return self._contexts.get(trace_id)

    def annotations_for(self, trace_id: str) -> Dict[str, Any]:
        """
        Return annotations for a specific trace_id, with any `None` values removed.
        """
        with self._lock:
            ann = self._annotations.get(trace_id) or {}
            if isinstance(ann, dict):
                return {k: v for k, v in ann.items() if v is not None}
            return {}

    def all_annotations(self) -> Dict[str, Dict[str, Any]]:
        """
        Return annotations for all traces, with `None` values removed.
        """
        with self._lock:
            out: Dict[str, Dict[str, Any]] = {}
            for tid, ann in self._annotations.items():
                if isinstance(ann, dict):
                    clean = {k: v for k, v in ann.items() if v is not None}
                    if clean:
                        out[tid] = clean
            return out

    # -------------------------
    # EXTRA DEBUG HELPERS
    # -------------------------

    def heatmap(self) -> Dict[str, Dict[str, Any]]:
        """
        Simple heatmap backing structure:

        {
          trace_id: {
            node_name: {
              "status": "...",
              "duration_ms": ...,
              "message": "...",
            },
            ...
          },
          ...
        }
        """
        per_trace: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            for e in self._events:
                bucket = per_trace.setdefault(e.trace_id, {})
                duration = float(e.extra.get("duration_ms") or 0)
                bucket[e.node] = {
                    "status": e.status,
                    "duration_ms": duration,
                    "message": e.message,
                }
        return per_trace

    def failure_map(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Map of trace_id -> list of failure events.
        """
        failures: Dict[str, List[Dict[str, Any]]] = {}
        with self._lock:
            for e in self._events:
                if e.status not in ("FAILED", "ERROR"):
                    continue
                failures.setdefault(e.trace_id, []).append(
                    {
                        "timestamp": e.timestamp,
                        "node": e.node,
                        "status": e.status,
                        "message": e.message,
                        "extra": e.extra,
                    }
                )
        return failures

    def trace_by_id(self, trace_id: str) -> List[Dict[str, Any]]:
        """
        Return all events for a given trace_id, ordered by time.
        """
        with self._lock:
            rows = [
                {
                    "trace_id": e.trace_id,
                    "timestamp": e.timestamp,
                    "node": e.node,
                    "status": e.status,
                    "message": e.message,
                    "extra": e.extra,
                }
                for e in self._events
                if e.trace_id == trace_id
            ]

        rows.sort(key=lambda r: r["timestamp"])
        return rows


# ---------------------------------------------------------
# GLOBAL SINGLETON
# ---------------------------------------------------------

tracer = GraphTracer()
