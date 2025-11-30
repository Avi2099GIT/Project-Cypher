# cloud/api/assistant/agents_dir/verifier_agent.py
from __future__ import annotations

from typing import Any, Dict, List


class VerifierAgent:
    """
    Step 6: Inspect tool results and decide if we are done or need follow-ups.
    For now we only annotate obvious failures; future: retries / clarifications.
    """

    def analyse(self, tools_meta: List[Dict[str, Any]]) -> Dict[str, Any]:
        failed = [t for t in tools_meta if "error" in t]
        return {
            "failed_count": len(failed),
            "failed_tools": [t.get("tool") for t in failed],
            "ok": len(failed) == 0,
        }
