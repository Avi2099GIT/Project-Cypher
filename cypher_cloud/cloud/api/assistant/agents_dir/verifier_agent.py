# cloud/api/assistant/agents_dir/verifier_agent.py
from __future__ import annotations

from typing import Any, Dict, List


class VerifierAgent:
    """
    Step 6: Inspect tool results and decide if execution was successful.

    Responsibilities:
      - detect failures
      - surface verified outputs (stdout, data, artifacts)
      - provide structured verification metadata for downstream agents
    """

    def analyse(self, tools_meta: List[Dict[str, Any]]) -> Dict[str, Any]:
        failed: List[Dict[str, Any]] = []
        verified_outputs: List[Dict[str, Any]] = []

        for t in tools_meta:
            tool_name = t.get("tool")

            # -------------------------
            # Failure detection
            # -------------------------
            if "error" in t:
                failed.append(t)
                continue

            # -------------------------
            # Successful tool output
            # -------------------------
            result = t.get("result")

            if not result:
                continue

            # MCP Shell: surface stdout/stderr
            if tool_name == "mcp:shell.exec":
                payload = result if isinstance(result, dict) else {}
                stdout = payload.get("stdout")
                stderr = payload.get("stderr")

                if stdout:
                    verified_outputs.append(
                        {
                            "tool": tool_name,
                            "type": "stdout",
                            "content": stdout,
                        }
                    )

                if stderr:
                    verified_outputs.append(
                        {
                            "tool": tool_name,
                            "type": "stderr",
                            "content": stderr,
                        }
                    )

            # Generic MCP / builtin tools
            else:
                verified_outputs.append(
                    {
                        "tool": tool_name,
                        "type": "result",
                        "content": result,
                    }
                )

        return {
            "ok": len(failed) == 0,
            "failed_count": len(failed),
            "failed_tools": [t.get("tool") for t in failed],
            "verified_outputs": verified_outputs,
        }
