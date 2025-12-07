# cloud/api/assistant/orchestrator/node.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable, List, Optional, Set, Iterable


class NodeStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    SKIPPED = auto()


# Signature: async def node_fn(ctx: ExecutionContext) -> Any
NodeFn = Callable[["ExecutionContext"], Awaitable[Any]]  # type: ignore[name-defined]


@dataclass
class GraphNode:
    """
    A single node in the orchestration graph.

    - name: unique id for this node
    - run: async function taking ExecutionContext and returning any result
    - requires: hard dependencies (must be SUCCESS)
    - optional_requires: soft deps; if they fail, this node can still run
    - allow_parallel: if False, node will always run in its own "layer"
    """
    name: str
    run: NodeFn
    requires: List[str] = field(default_factory=list)
    optional_requires: List[str] = field(default_factory=list)
    allow_parallel: bool = True

    def all_dependencies(self) -> Set[str]:
        return set(self.requires) | set(self.optional_requires)

    def __repr__(self) -> str:
        return (
            f"GraphNode(name={self.name!r}, "
            f"requires={self.requires}, optional_requires={self.optional_requires})"
        )
