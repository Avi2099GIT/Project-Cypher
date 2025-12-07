from __future__ import annotations

from typing import Any, Dict, List
import logging

from cloud.api.assistant.memory import memory_service
from cloud.api.assistant.memory.semantic import semantic_memory

logger = logging.getLogger(__name__)


class MemoryNode:
    """
    Retrieval-focused Memory Node.

    Responsibilities:
      - Fetch recent episodic memory for the device
      - Run semantic search against semantic memory
      - Inject both into ctx.extras["memory"]

    This is READ-ONLY. It does NOT write memory.
    """

    def __init__(self, recent_limit: int = 15) -> None:
        self.recent_limit = recent_limit

    async def run(self, ctx) -> Dict[str, Any]:
        """
        Called by the graph as an async node:
            await memory_node_agent.run(ctx)

        ctx provides:
          - ctx.device
          - ctx.message
        """
        device = getattr(ctx, "device", None) or {"device_id": "local-dev"}

        # --- Episodic memory ---
        try:
            episodes = memory_service.get_recent_episodes(
                device=device,
                limit=self.recent_limit,
            )
        except Exception:
            logger.exception("MemoryNode failed to retrieve episodes")
            episodes = []

        # --- Semantic hits (vector search) ---
        semantic_hits: List[Dict[str, Any]] = []
        try:
            if getattr(ctx, "message", None):
                semantic_hits = semantic_memory.search(
                    device=device,
                    query=ctx.message,
                    kind=None,
                    top_k=5,
                )
        except Exception:
            logger.exception("MemoryNode failed to run semantic search")
            semantic_hits = []

        memory_blob: Dict[str, Any] = {
            "recent_episodes": episodes,
            "semantic_hits": semantic_hits,
            "device_id": device.get("device_id") or device.get("id"),
        }

        ctx.extras["memory"] = memory_blob
        return memory_blob
