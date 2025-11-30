# cloud/api/assistant/agents_dir/safety_agent.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple


class SafetyAgent:
    """
    Step 3: Filter/annotate intents based on safety rules.

    For now this is intentionally simple; most OS safety is enforced
    inside the actual tools (e.g. os_control whitelisting).
    """

    def filter(
        self,
        intents: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        safe: List[Dict[str, Any]] = []
        blocked: List[Dict[str, Any]] = []

        for it in intents:
            itype = it.get("type")
            params = it.get("params") or {}

            # Example: block obviously destructive os_control intents
            if itype == "os_control":
                action = (params.get("action") or "").lower()
                # we only explicitly allow the safe ones here
                if action in ("open_app", "open_url", "lock", "list_processes"):
                    safe.append(it)
                elif not action:
                    # let the tool heuristics decide (still safe)
                    safe.append(it)
                else:
                    it["reason"] = f"Blocked dangerous OS action: {action!r}"
                    blocked.append(it)
            else:
                safe.append(it)

        return safe, blocked
