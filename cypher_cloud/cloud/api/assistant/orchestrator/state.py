# cloud/api/assistant/orchestrator/state.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time
import uuid
import logging

from .node import NodeStatus

logger = logging.getLogger(__name__)


@dataclass
class NodeResult:
    name: str
    status: NodeStatus
    output: Any = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at) * 1000.0


@dataclass
class ExecutionContext:
    """
    Shared state for a single Cypher orchestration run.

    Holds:
      - user message
      - history
      - device info
      - arbitrary extras (e.g. auth, metadata)
      - per-node results
    """
    message: str
    history: Any
    device: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    node_results: Dict[str, NodeResult] = field(default_factory=dict)

    def set_result(
        self,
        name: str,
        status: NodeStatus,
        output: Any = None,
        error: Optional[str] = None,
        started_at: Optional[float] = None,
        finished_at: Optional[float] = None,
    ) -> NodeResult:
        res = NodeResult(
            name=name,
            status=status,
            output=output,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
        )
        self.node_results[name] = res
        return res

    def get_result(self, name: str) -> Optional[NodeResult]:
        return self.node_results.get(name)

    def get_output(self, name: str, default: Any = None) -> Any:
        res = self.get_result(name)
        if not res or res.status != NodeStatus.SUCCESS:
            return default
        return res.output

    def as_dict(self) -> Dict[str, Any]:
        """
        Lightweight view useful for logging or debugging.
        Does NOT serialize full outputs (they may be large).
        """
        return {
            "trace_id": self.trace_id,
            "message": self.message,
            "device": self.device,
            "created_at": self.created_at,
            "nodes": {
                name: {
                    "status": res.status.name,
                    "error": res.error,
                    "duration_ms": res.duration_ms,
                }
                for name, res in self.node_results.items()
            },
        }

    def log_summary(self) -> None:
        try:
            summary = self.as_dict()
            logger.info("Graph run summary trace_id=%s nodes=%d",
                        self.trace_id, len(summary["nodes"]))
        except Exception:
            logger.exception("Failed to log graph summary.")
