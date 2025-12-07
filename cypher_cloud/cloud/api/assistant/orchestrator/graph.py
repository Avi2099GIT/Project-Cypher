from __future__ import annotations

from typing import Dict, List, Optional, Set
import asyncio
import logging
import time
import traceback

from .node import GraphNode, NodeStatus
from .state import ExecutionContext
from .tracer import tracer as global_tracer

logger = logging.getLogger(__name__)


class AgentGraph:
    """
    Dependency-aware execution graph.

    Nodes:
       - Resolve dependencies
       - Run parallel-safe nodes concurrently
       - Track state and trace events
    """

    def __init__(self, name: str = "cypher-core") -> None:
        self.name = name
        self._nodes: Dict[str, GraphNode] = {}

    def add_node(self, node: GraphNode) -> None:
        if node.name in self._nodes:
            raise ValueError(f"Duplicate node {node.name}")
        self._nodes[node.name] = node

    def get_node(self, name: str) -> GraphNode:
        return self._nodes[name]

    @property
    def nodes(self) -> Dict[str, GraphNode]:
        return dict(self._nodes)

    async def run(
        self,
        ctx: ExecutionContext,
        tracer=None,
    ) -> ExecutionContext:

        tracer = tracer or global_tracer
        logger.info("Running graph=%s trace=%s", self.name, ctx.trace_id)

        # Initialize state
        for name in self._nodes:
            if ctx.get_result(name) is None:
                ctx.set_result(name, status=NodeStatus.PENDING)

        remaining: Set[str] = set(self._nodes)

        while remaining:
            runnable = self._find_runnable(remaining, ctx)

            if not runnable:
                self._mark_unreachable(remaining, ctx, tracer)
                break

            layer = [self._nodes[name] for name in runnable]
            await self._run_layer(layer, remaining, ctx, tracer)

        return ctx

    def _find_runnable(self, remaining: Set[str], ctx: ExecutionContext) -> List[str]:
        runnable = []

        for name in list(remaining):
            res = ctx.get_result(name)
            if not res or res.status != NodeStatus.PENDING:
                continue

            node = self._nodes[name]
            deps = node.requires

            dep_states = []
            for d in deps:
                r = ctx.get_result(d)
                dep_states.append(r.status if r else NodeStatus.PENDING)

            if any(s in (NodeStatus.FAILED, NodeStatus.SKIPPED) for s in dep_states):
                ctx.set_result(name, status=NodeStatus.SKIPPED, error="Hard dep failed")
                continue

            if all(s == NodeStatus.SUCCESS for s in dep_states):
                runnable.append(name)

        return runnable

    async def _run_layer(
        self,
        nodes: List[GraphNode],
        remaining: Set[str],
        ctx: ExecutionContext,
        tracer,
    ):
        parallel = [n for n in nodes if n.allow_parallel]
        serial = [n for n in nodes if not n.allow_parallel]

        if parallel:
            await self._run_parallel(parallel, remaining, ctx, tracer)

        for node in serial:
            await self._run_one(node, remaining, ctx, tracer)

    async def _run_parallel(self, nodes, remaining, ctx, tracer):
        tasks = [
            self._run_one(n, remaining, ctx, tracer, remove=False)
            for n in nodes
        ]
        await asyncio.gather(*tasks)
        for n in nodes:
            remaining.discard(n.name)

    async def _run_one(
        self,
        node: GraphNode,
        remaining: Set[str],
        ctx: ExecutionContext,
        tracer,
        remove: bool = True,
    ):

        name = node.name
        start = time.time()

        tracer.record(trace_id=ctx.trace_id,node=name, status=NodeStatus.RUNNING, message="start")
        ctx.set_result(name, status=NodeStatus.RUNNING, started_at=start)

        try:
            output = await node.run(ctx)
            end = time.time()

            ctx.set_result(
                name,
                status=NodeStatus.SUCCESS,
                output=output,
                finished_at=end,
            )

            tracer.record(
                trace_id=ctx.trace_id,
                node=name,
                status=NodeStatus.SUCCESS,
                message="done",
                extra={"duration_ms": (end - start) * 1000},
            )

        except Exception as e:
            end = time.time()
            tb = traceback.format_exc()

            ctx.set_result(
                name,
                status=NodeStatus.FAILED,
                error=str(e),
                finished_at=end,
            )

            tracer.record(
                trace_id=ctx.trace_id,
                node=name,
                status=NodeStatus.FAILED,
                message=str(e),
                extra={"traceback": tb},
            )

        if remove:
            remaining.discard(name)

    def _mark_unreachable(self, remaining, ctx, tracer):
        msg = f"Unreachable nodes in graph={self.name}: {sorted(remaining)}"
        logger.error(msg)

        for name in remaining:
            ctx.set_result(name, status=NodeStatus.FAILED, error=msg)
            tracer.record(trace_id=ctx.trace_id,node=name, status=NodeStatus.FAILED, message="graph deadlock")
