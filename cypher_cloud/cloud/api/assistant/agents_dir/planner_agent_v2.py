from __future__ import annotations

from typing import Any, Dict, List
import logging
from dataclasses import dataclass, field
import re
from cloud.api.assistant.mcp.registry import mcp_registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# DATA MODELS (STABLE CONTRACT)
# ---------------------------------------------------------

@dataclass
class PlanStep:
    tool: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    steps: List[PlanStep]
    explanation: str
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    rejected: List[str] = field(default_factory=list)


# ---------------------------------------------------------
# PLANNER V2 (FINAL, HARDENED)
# ---------------------------------------------------------

class PlannerV2:
    """
    PlannerV2 converts SAFE intents OR raw commands into executable steps.

    Guarantees:
    - Never raises for missing intents
    - Always returns deterministic plans
    - Supports MCP + local tools
    """

    # -----------------------------------------------------
    # CANDIDATE GENERATION
    # -----------------------------------------------------

    def generate_candidates(
        self,
        safe_intents: List[Dict[str, Any]],
        extras: Dict[str, Any],
    ) -> List[ExecutionPlan]:
        
        message = extras.get("message", "").strip().lower()

        # 🔴 FORCE_TOOLS FALLBACK (NO INTENTS REQUIRED)
        if not safe_intents and message:
            if message.startswith(("run ", "execute ", "exec ")):
                cmd = message.replace("run", "", 1).strip()
                if cmd:
                    return [
                        ExecutionPlan(
                            steps=[
                                PlanStep(
                                    tool="mcp:shell.exec",
                                    args={"cmd": cmd},
                                )
                            ],
                            explanation="Forced shell execution (no intents)",
                            score_breakdown={"confidence": 0.95},
                        )
                    ]

            if "time" in message:
                return [
                    ExecutionPlan(
                        steps=[PlanStep(tool="time", args={})],
                        explanation="Forced time tool (no intents)",
                        score_breakdown={"confidence": 0.9},
                    )
                ]


        candidates: List[ExecutionPlan] = []

        # -------------------------
        # 1) INTENT-BASED PLANS
        # -------------------------

        for intent in safe_intents or []:
            itype = intent.get("type")
            payload = intent.get("params") or {}

            if itype == "time":
                candidates.append(
                    ExecutionPlan(
                        steps=[PlanStep(tool="time")],
                        explanation="User asked for current time",
                        score_breakdown={"confidence": 0.95},
                    )
                )
                continue

            if itype == "weather":
                candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="weather",
                                args={"location": payload.get("location")},
                            )
                        ],
                        explanation="User asked for weather",
                        score_breakdown={"confidence": 0.9},
                    )
                )
                continue

            if itype == "web_search":
                candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="web_search",
                                args={"query": payload.get("query")},
                            )
                        ],
                        explanation="User requested web search",
                        score_breakdown={"confidence": 0.85},
                    )
                )
                continue

            if itype == "calendar":
                candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="calendar_google",
                                args=payload,
                            )
                        ],
                        explanation="User requested calendar action",
                        score_breakdown={"confidence": 0.9},
                    )
                )
                continue

            if itype == "google_tasks":
                candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="google_tasks",
                                args=payload,
                            )
                        ],
                        explanation="User requested task action",
                        score_breakdown={"confidence": 0.9},
                    )
                )
                continue

            if itype == "notes":
                candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="notes",
                                args=payload,
                            )
                        ],
                        explanation="User requested notes action",
                        score_breakdown={"confidence": 0.9},
                    )
                )
                continue

            if itype == "os_control":
                candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="os_control",
                                args=payload,
                            )
                        ],
                        explanation="User requested OS operation",
                        score_breakdown={"confidence": 0.9},
                    )
                )
                continue

            if itype == "shell":
                cmd = payload.get("cmd")
                if cmd:
                    candidates.append(
                        ExecutionPlan(
                            steps=[
                                PlanStep(
                                    tool="mcp:shell.exec",
                                    args={"cmd": cmd},
                                )
                            ],
                            explanation="Shell command via MCP (intent)",
                            score_breakdown={"confidence": 0.9},
                        )
                    )

        # -------------------------------------------------
        # 2) DYNAMIC CONNECT HEURISTICS
        # -------------------------------------------------
        if "connect" in message and ("mcp" in message or "server" in message):
             # SQLite Real World Test
             if "sqlite" in message:
                 candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="connect_mcp_stdio",
                                args={
                                    "name": "sqlite",
                                    "command": "python",
                                    "args": ["-m", "mcp_server_sqlite", "--db-path", "test.db"]
                                }
                            )
                        ],
                        explanation="Test: Connecting to Real World SQLite MCP server",
                        score_breakdown={"confidence": 0.99}
                    )
                 )
             # Time Real World Test
             elif "time mcp" in message:
                 candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="connect_mcp_stdio",
                                args={
                                    "name": "time_remote",
                                    "command": "python",
                                    "args": ["-m", "mcp_server_time"]
                                }
                            )
                        ],
                        explanation="Test: Connecting to Real World Time MCP server",
                        score_breakdown={"confidence": 0.99}
                    )
                 )
             # Fetch Real World Test
             elif "fetch" in message and ("mcp" in message or "connect" in message):
                 candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="connect_mcp_stdio",
                                args={
                                    "name": "fetch_remote",
                                    "command": "python",
                                    "args": ["-m", "mcp_server_fetch"]
                                }
                            )
                        ],
                        explanation="Test: Connecting to Real World Fetch MCP server",
                        score_breakdown={"confidence": 0.99}
                    )
                 )
             # Default Demo
             else:
                 candidates.append(
                    ExecutionPlan(
                        steps=[
                            PlanStep(
                                tool="connect_mcp_stdio",
                                args={
                                    "name": "demo_dynamic",
                                    "command": "python",
                                    "args": ["demo_mcp_server.py"]
                                }
                            )
                        ],
                        explanation="Test: Connecting to demo Dynamic MCP server",
                        score_breakdown={"confidence": 0.99}
                    )
                 )

        # -------------------------------------------------
        # 3) MCP DYNAMIC DISCOVERY & HEURISTICS
        # -------------------------------------------------
        try:
            for name, client in mcp_registry.list().items():
                if not getattr(client, "enabled", False):
                    continue

                # --- CLAUDE MCP HEURISTICS ---
                if name == "claude":
                    if "claude" in message or "ask" in message:
                        query = message
                        # clean up "ask claude"
                        if message.lower().startswith("ask claude"):
                            query = message[10:].strip()
                        candidates.append(
                            ExecutionPlan(
                                steps=[PlanStep(tool="mcp:claude.ask", args={"query": query})],
                                explanation="Asking Claude via ClaudeMCP",
                                score_breakdown={"confidence": 0.95}
                            )
                        )

                # --- FETCH MCP HEURISTICS ---
                if name == "fetch_remote":
                    if "fetch" in message:
                         url_match = re.search(r'https?://[^\s]+', message)
                         if url_match:
                             url = url_match.group(0)
                             candidates.append(
                                ExecutionPlan(
                                    steps=[PlanStep(tool="mcp:fetch_remote.fetch", args={"url": url})],
                                    explanation="Fetching URL via FetchMCP",
                                    score_breakdown={"confidence": 0.95}
                                )
                             )

                # --- TIME MCP HEURISTICS ---
                if name == "time_remote":
                     if "what time" in message or "current time" in message:
                         candidates.append(
                            ExecutionPlan(
                                steps=[PlanStep(tool="mcp:time_remote.get_current_time", args={})],
                                explanation="Getting time via Remote Time MCP",
                                score_breakdown={"confidence": 0.95}
                            )
                         )

                # --- MATH MCP HEURISTICS ---
                if name == "math":
                    # Check for basic arithmetic patterns
                    # "5 + 5", "add 5 and 5", "multiply 10 by 20"
                    if any(kw in message for kw in ["add", "plus", "+"]):
                        digits = re.findall(r"-?\d+\.?\d*", message)
                        if len(digits) >= 2:
                            candidates.append(
                                ExecutionPlan(
                                    steps=[
                                        PlanStep(
                                            tool="mcp:math.add",
                                            args={"a": digits[0], "b": digits[1]},
                                        )
                                    ],
                                    explanation="Math additions via MathMCP",
                                    score_breakdown={"confidence": 0.95},
                                )
                            )
                    
                    if any(kw in message for kw in ["multiply", "times", "*", "product"]):
                        digits = re.findall(r"-?\d+\.?\d*", message)
                        if len(digits) >= 2:
                            candidates.append(
                                ExecutionPlan(
                                    steps=[
                                        PlanStep(
                                            tool="mcp:math.multiply",
                                            args={"a": digits[0], "b": digits[1]},
                                        )
                                    ],
                                    explanation="Math multiplication via MathMCP",
                                    score_breakdown={"confidence": 0.95},
                                )
                            )

                # --- GITHUB MCP HEURISTICS ---
                elif name == "github":
                    if "pull request" in message or " pr " in message:
                        candidates.append(
                            ExecutionPlan(
                                steps=[
                                    PlanStep(
                                        tool="mcp:github.list_pull_requests",
                                        args={},
                                    )
                                ],
                                explanation="Listing PRs via GitHubMCP",
                                score_breakdown={"confidence": 0.95},
                            )
                        )

                # --- DEMO DYNAMIC MCP HEURISTICS ---
                elif name == "demo_dynamic":
                     if "echo" in message and "upper" in message:
                         text = message.replace("echo", "").replace("upper", "").strip()
                         candidates.append(
                            ExecutionPlan(
                                steps=[
                                    PlanStep(
                                        tool="mcp:demo_dynamic.echo_upper",
                                        args={"text": text},
                                    )
                                ],
                                explanation="Echo Upper via DemoMCP",
                                score_breakdown={"confidence": 0.95},
                            )
                        )

                # --- SQLITE MCP HEURISTICS ---
                elif name == "sqlite":
                    if "query" in message or "sql" in message or "select" in message.lower():
                        # Extract query roughly
                        query = message
                        for prefix in ["run query", "execute query", "query", "sql"]:
                            if message.lower().startswith(prefix):
                                query = message[len(prefix):].strip()
                                break
                        
                        # Decide tool based on keywords
                        is_write = any(kw in query.lower() for kw in ["create", "insert", "update", "delete", "drop", "alter"])
                        tool_name = "mcp:sqlite.write_query" if is_write else "mcp:sqlite.read_query"
                        
                        candidates.append(
                            ExecutionPlan(
                                steps=[PlanStep(tool=tool_name, args={"query": query})],
                                explanation=f"Executing SQLite {tool_name}",
                                score_breakdown={"confidence": 0.95}
                            )
                        )

                # --- DOCKER MCP HEURISTICS ---
                elif name == "docker":
                    if "docker" in message or "container" in message:
                        candidates.append(
                            ExecutionPlan(
                                steps=[
                                    PlanStep(
                                        tool="mcp:docker.list_containers",
                                        args={},
                                    )
                                ],
                                explanation="Listing containers via DockerMCP",
                                score_breakdown={"confidence": 0.95},
                            )
                        )

                # --- PLAYWRIGHT MCP HEURISTICS ---
                elif name == "playwright":
                    if "browse" in message or "page title" in message:
                         # Extraction logic for URL would be ideal, but for now assuming arg is passed or heuristic match
                         # Simple demo: if they provide a url in message
                         url_match = re.search(r'https?://[^\s]+', message)
                         if url_match:
                            candidates.append(
                                ExecutionPlan(
                                    steps=[
                                        PlanStep(
                                            tool="mcp:playwright.get_title",
                                            args={"url": url_match.group(0)},
                                        )
                                    ],
                                    explanation="Getting page title via PlaywrightMCP",
                                    score_breakdown={"confidence": 0.95},
                                )
                            )

                # --- CLAUDE MCP HEURISTICS ---
                elif name == "claude":
                    if "ask claude" in lower_msg or "claude says" in lower_msg:
                        print(f"PLANNER DEBUG: Triggering Claude Heuristic for '{message}'")
                        prompt = message.replace("ask claude", "").replace("Ask Claude", "").replace("claude says", "").strip()
                        candidates.append(
                            ExecutionPlan(
                                steps=[
                                    PlanStep(
                                        tool="mcp:claude.ask",
                                        args={"query": prompt, "model": "claude-3-5-sonnet-20241022"},
                                    )
                                ],
                                explanation="Querying remote Claude API (CRITICAL: MUST USE TOOL)",
                                score_breakdown={"confidence": 0.99},
                            )
                        )

                # --- SHELL MCP HEURISTICS ---
                elif name == "shell":
                    if message.startswith("shell "):
                         cmd = message.replace("shell", "", 1).strip()
                         if cmd:
                            candidates.append(
                                ExecutionPlan(
                                    steps=[
                                        PlanStep(
                                            tool="mcp:shell.exec",
                                            args={"cmd": cmd},
                                        )
                                    ],
                                    explanation="Explicit shell command via ShellMCP",
                                    score_breakdown={"confidence": 0.95},
                                )
                            )

        except Exception as e:
            logger.warning("MCP discovery failed: %s", e)

        # -------------------------------------------------
        # 2) FALLBACK: FORCE_TOOLS + RAW COMMAND
        # -------------------------------------------------

        if not candidates:
            message = (extras.get("message") or "").strip()
            lower = message.lower()

            if lower.startswith("run command"):
                cmd = message[len("run command"):].strip()
                if cmd:
                    candidates.append(
                        ExecutionPlan(
                            steps=[
                                PlanStep(
                                    tool="mcp:shell.exec",
                                    args={"cmd": cmd},
                                )
                            ],
                            explanation="Fallback shell execution (force_tools)",
                            score_breakdown={"confidence": 0.9},
                        )
                    )

        return candidates

    # -----------------------------------------------------
    # BEST PLAN SELECTION
    # -----------------------------------------------------

    def pick_best(
        self,
        candidates: List[ExecutionPlan],
        extras: Dict[str, Any],
    ) -> ExecutionPlan:

        if not candidates:
            raise RuntimeError("pick_best called with no candidates")

        def score(plan: ExecutionPlan) -> float:
            return plan.score_breakdown.get("confidence", 0.0)

        return max(candidates, key=score)
