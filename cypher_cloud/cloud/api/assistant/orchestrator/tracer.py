from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time
import threading
import logging
from collections import defaultdict, Counter
import datetime
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

    REQUIRED by:
      - cypher_graph.py
      - executor.py
      - failure_node.py
      - React Trace Inspector
    """

    def __init__(self) -> None:
        self._events: List[GraphEvent] = []
        self._lock = threading.Lock()
        self._contexts: dict[str, dict] = {}

    def new_trace(self) -> str:
        """
        Create a new trace_id. The graph / router is responsible for
        passing this ID through ExecutionContext so all nodes share it.
        """
        return str(uuid.uuid4())

    def attach_context(self, trace_id: str, ctx: dict) -> None:
        with self._lock:
            self._contexts[trace_id] = ctx


    def get_context(self, trace_id: str):
        with self._lock:
            return self._contexts.get(trace_id)


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

        logger.debug(
            "TRACE %s | %s | %s", evt.node, evt.status, evt.message
        )

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

    # -------------------------
    # UI SUPPORT METHODS
    # -------------------------

    def timeline(self):
        """Events ordered by time (for UI replay)"""
        return sorted(self.to_dict(), key=lambda e: e["timestamp"])

    def slowest_nodes(self, top=5):
        """Nodes with highest cumulative runtime"""
        durations = {}

        for e in self._events:
            if e.message == "success":
                ms = e.extra.get("duration_ms", 0)
                durations[e.node] = durations.get(e.node, 0) + ms

        return sorted(
            [{"node": k, "total_ms": v} for k, v in durations.items()],
            key=lambda x: x["total_ms"],
            reverse=True,
        )[:top]

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
        
    def heatmap(self, bucket="minute"):

        buckets = defaultdict(lambda: defaultdict(int))

        for e in self._events:
            ts = datetime.datetime.fromtimestamp(e.timestamp)
            key = ts.strftime("%Y-%m-%d %H:%M")  # per-minute buckets
            buckets[key][e.node] += 1

        return [
            {"bucket": k, "data": v}
            for k, v in buckets.items()
        ]
    
    def slow_nodes(self):
        stats = defaultdict(lambda: {"total": 0, "count": 0})

        for e in self._events:
            d = e.extra.get("duration_ms")
            if d:
                stats[e.node]["total"] += d
                stats[e.node]["count"] += 1

        return [
            {
                "node": n,
                "total_ms": v["total"],
                "count": v["count"],
                "avg": round(v["total"] / max(v["count"], 1), 2)
            }
            for n, v in stats.items()
        ]
    
    def failure_map(self):
        c = Counter()

        for e in self._events:
            if e.status in ("FAILED", "ERROR"):
                c[e.node] += 1

        return dict(c)
    
    def trace_by_id(self, tid: str):
        return [e for e in self._events if e.trace_id == tid]






# ---------------------------------------------------------
# GLOBAL SINGLETON (DO NOT DELETE)
# ---------------------------------------------------------

tracer = GraphTracer()
