from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import logging

from .graph import AgentGraph
from .state import ExecutionContext
from cloud.api.assistant.orchestrator.tracer import tracer as global_tracer

logger = logging.getLogger(__name__)


class GraphExecutor:
    """
    High-level execution entrypoint for Cypher orchestration.
    """

    def __init__(self, graph: AgentGraph) -> None:
        self.graph = graph

    async def run_query(
        self,
        *,
        message: str,
        history: List[Dict[str, Any]],
        device: Optional[Dict[str, Any]] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> Tuple[ExecutionContext, object]:

        device = device or {}
        extras = extras or {}

        ctx = ExecutionContext(
            message=message,
            history=history,
            device=device,
            extras=extras,
        )

        tracer = global_tracer

        logger.info(
            "GraphExecutor starting | trace_id=%s graph=%s device=%s",
            ctx.trace_id,
            self.graph.name,
            device.get("device_id") or device.get("id") or "unknown",
        )

        # ✅ call graph with tracer
        ctx = await self.graph.run(ctx, tracer)

        logger.info(
            "GraphExecutor finished | trace_id=%s graph=%s",
            ctx.trace_id,
            self.graph.name,
        )

        # ✅ Attach full execution context to tracer so /debug/plan can find it
        try:
            tracer.attach_context(ctx.trace_id, ctx)
        except Exception:
            logger.exception(
                "GraphExecutor: failed to attach context for trace_id=%s",
                ctx.trace_id,
            )

        return ctx, tracer
