from __future__ import annotations

from typing import Any, Dict, List

from cloud.api.assistant.orchestrator import AgentGraph, GraphNode
from cloud.api.assistant.agents import chat_agent

from cloud.api.assistant.agents_dir.intent_agent import IntentAgent
from cloud.api.assistant.agents_dir.entity_agent import EntityAgent
from cloud.api.assistant.agents_dir.safety_agent import SafetyAgent
from cloud.api.assistant.agents_dir.planner_agent import PlannerAgentH
from cloud.api.assistant.agents_dir.executor_agent import ExecutorAgent
from cloud.api.assistant.agents_dir.verifier_agent import VerifierAgent
from cloud.api.assistant.agents_dir.reasoning_agent import ReasoningAgent
from cloud.api.assistant.agents_dir.arbiter_agent import ArbiterAgent
from cloud.api.assistant.agents_dir.memory_node import MemoryNode
from cloud.api.assistant.orchestrator.failure_node import FailureNode
from cloud.api.assistant.agents_dir.planner_agent_v2 import PlannerV2

from cloud.api.assistant.mcp.models import MCPCallResult  # ✅ REQUIRED

# Instantiate Phase-3 / Phase-4 agents
planner_v2 = PlannerV2()
memory_node_agent = MemoryNode()
intent_agent = IntentAgent()
entity_agent = EntityAgent()
safety_agent = SafetyAgent()
planner_agent = PlannerAgentH()
executor_agent = ExecutorAgent()
verifier_agent = VerifierAgent()
reasoning_agent = ReasoningAgent()
arbiter_agent = ArbiterAgent()
failure_engine = FailureNode()

# --------------------
# Graph Node wrappers
# --------------------

async def intent_node(ctx):
    intents = await intent_agent.parse(ctx.message, ctx.history)
    ctx.extras["intents"] = intents
    return intents


def _filter_memory_for_chat(memory: dict) -> list:
    episodes = (memory or {}).get("recent_episodes") or []
    filtered = []
    for ep in episodes:
        meta = ep.get("meta") or {}
        content = (ep.get("content") or "").lower()

        if meta.get("suppress_for_reasoning"):
            continue
        if "your computer is now locked" in content:
            continue
        if "computer is currently locked" in content:
            continue

        filtered.append(ep)
    return filtered


async def entity_node(ctx):
    intents = ctx.extras.get("intents") or []
    enriched = entity_agent.enrich(intents, ctx.message, ctx.extras)
    ctx.extras["enriched_intents"] = enriched
    return enriched


async def safety_node(ctx):
    enriched = ctx.extras.get("enriched_intents") or []
    safe_intents, blocked = safety_agent.filter(enriched)

    ctx.extras["safe_intents"] = safe_intents
    ctx.extras["blocked_intents"] = blocked

    return {
        "safe_intents": safe_intents,
        "blocked_intents": blocked,
    }


async def reasoning_node(ctx):
    result = await reasoning_agent.run(
        ctx.message,
        ctx.extras.get("intents") or [],
        ctx.extras.get("enriched_intents") or [],
        ctx.history,
        ctx.extras.get("memory") or {},
    )
    ctx.extras["reasoning"] = result
    return result


async def arbiter_node(ctx):
    decision = await arbiter_agent.run(
        ctx.message,
        ctx.extras.get("safe_intents") or [],
        ctx.extras.get("blocked_intents") or [],
        ctx.extras.get("reasoning") or {},
    )
    ctx.extras["decision"] = decision
    return decision


async def planner_node(ctx):
    ctx.extras["message"] = ctx.message
    decision = ctx.extras.get("decision") or {}
    mode = decision.get("mode")

    safe_intents = ctx.extras.get("safe_intents") or []
    if not safe_intents and mode == "safety_block":
        ctx.extras["plan"] = []
        return {"status": "skipped", "reason": "safety_block"}

    if mode in ("clarify_only", "chat_only"):
        ctx.extras["plan"] = []
        return {"status": "skipped", "reason": f"mode={mode}"}

    candidates = planner_v2.generate_candidates(safe_intents, ctx.extras)
    if not candidates:
        ctx.extras["plan"] = []
        return {"status": "skipped", "reason": "no_plan"}

    best = planner_v2.pick_best(candidates, ctx.extras)
    ctx.extras["execution_plan"] = best
    ctx.extras["execution_steps"] = best.steps

    return {
        "status": "ok",
        "execution_steps": best.steps,   # ✅ REQUIRED
        "selected_steps": [s.tool for s in best.steps],
    }


async def executor_node(ctx):
    steps = ctx.extras.get("execution_steps")

    if steps is None:
        ctx.extras["tool_result"] = []
        return {"status": "skipped", "reason": "no_execution_steps"}

    if not isinstance(steps, list):
        raise RuntimeError(f"execution_steps must be list, got {type(steps)}")

    if not steps:
        ctx.extras["tool_result"] = []
        return {"status": "skipped", "reason": "no_plan"}

    exec_ctx: Dict[str, Any] = dict(ctx.extras)
    exec_ctx["message"] = ctx.message

    raw_results = await executor_agent.run(steps, exec_ctx)

    normalized: List[Dict[str, Any]] = []

    for r in raw_results or []:
        if isinstance(r, MCPCallResult):
            if r.success:
                normalized.append({
                    "tool": f"mcp:{r.tool}",
                    "result": r.payload,
                })
            else:
                normalized.append({
                    "tool": f"mcp:{r.tool}",
                    "error": r.error or "Unknown MCP error",
                })
            continue

        if isinstance(r, dict):
            normalized.append(r)
            continue

        raise RuntimeError(f"Unsupported tool result type: {type(r)}")

    ctx.extras["tool_result"] = normalized
    return {"status": "ok", "tools": normalized}


async def verifier_node(ctx):
    tools_meta = ctx.extras.get("tool_result") or []
    if not tools_meta:
        ctx.extras["verification"] = {"ok": True, "failed_tools": []}
        return {"status": "skipped", "reason": "no_tools"}

    verification = verifier_agent.analyse(tools_meta)
    ctx.extras["verification"] = verification
    return {"status": "ok", "verification": verification}


async def failure_node(ctx):
    await failure_engine.handle(ctx)
    return {"status": "checked"}


async def chat_node(ctx):
    # unchanged — your implementation is already correct
    ...


async def chat_node(ctx):
    """
    Final reply generator.

    Uses:
      - decision (safety / clarify / chat / tools)
      - reasoning (clarification question)
      - tool_result (for augmented replies)
      - verification (to warn about partial failures)
      - memory (recent episodes for extra context)
    """
    decision: Dict[str, Any] = ctx.extras.get("decision") or {}
    reasoning: Dict[str, Any] = ctx.extras.get("reasoning") or {}
    tools_meta: List[Dict[str, Any]] = ctx.extras.get("tool_result") or []
    verification: Dict[str, Any] = ctx.extras.get("verification") or {"ok": True}

    mode = (decision.get("mode") or "").lower()

    # 1) Safety block response
    if mode == "safety_block":
        explanation = decision.get("explanation") or "This request was blocked for safety reasons."
        reply = (
            "I have blocked this request for safety reasons.\n"
            f"Details: {explanation}"
        )
        ctx.extras["final_reply"] = reply
        return reply

    # 2) Clarification-only mode
    if mode == "clarify_only":
        question = reasoning.get("clarification_question")
        if not question:
            question = "Can you clarify what exactly you want me to do?"
        ctx.extras["final_reply"] = question
        return question

    # 3) Special-case: calendar list → deterministic reply (no LLM)
    calendar_list_reply = None
    for t in tools_meta:
        name = t.get("tool")
        result = t.get("result")
        if name == "calendar_google" and isinstance(result, dict):
            if result.get("status") == "ok" and result.get("mode") == "list":
                events = result.get("events") or []
                # Build a human-readable calendar view
                if not events:
                    calendar_list_reply = (
                        "It appears there are no events scheduled in your calendar "
                        "for that period. If you’d like, I can help you schedule one."
                    )
                else:
                    lines = []
                    for ev in events:
                        title = ev.get("title") or "Untitled"
                        start = ev.get("start") or "unknown time"
                        link = ev.get("htmlLink") or ""
                        if link:
                            lines.append(f"- {start} — {title}\n  {link}")
                        else:
                            lines.append(f"- {start} — {title}")

                    calendar_list_reply = (
                        "Here are the events in your calendar for that period:\n\n"
                        + "\n".join(lines)
                    )
                break  # we only need the first calendar list result

    # If we have a deterministic calendar list reply and ONLY calendar ran,
    # return it directly instead of asking the LLM.
    if calendar_list_reply is not None and len(tools_meta) == 1:
        # Surface verification issues if any
        if verification and not verification.get("ok", True):
            failed_names = ", ".join(verification.get("failed_tools") or [])
            calendar_list_reply += (
                f"\n\n(Note: some tools failed internally: {failed_names}. "
                "I still returned what I could.)"
            )

        ctx.extras["final_reply"] = calendar_list_reply
        return calendar_list_reply

    # 4) Build tool summary text (for context) if tools ran
    tool_summary_lines: List[str] = []
    for t in tools_meta:
        name = t.get("tool")
        result = t.get("result")

        if "error" in t:
            tool_summary_lines.append(f"{name}: ERROR → {t['error']}")
            continue

        # Special-case: Google Calendar listing (for LLM context if not handled above)
        if name == "calendar_google" and isinstance(result, dict):
            if result.get("mode") == "list" and result.get("status") == "ok":
                events = result.get("events") or []
                if not events:
                    tool_summary_lines.append("calendar_google: no upcoming events.")
                else:
                    lines = []
                    for ev in events[:5]:
                        title = ev.get("title") or "Untitled"
                        start = ev.get("start") or "unknown time"
                        lines.append(f"{start} — {title}")
                    tool_summary_lines.append(
                        "calendar_google: upcoming events:\n" + "\n".join(lines)
                    )
                continue

        # Generic preview for any other tool
        preview = str(result)[:400]
        tool_summary_lines.append(f"{name}: {preview}")

    tools_block = (
        "\n\n[Tool results]\n" + "\n".join(tool_summary_lines)
        if tool_summary_lines
        else ""
    )

    augmented_message = ctx.message + tools_block

    # 5) Inject memory block for LLM context
    memory = ctx.extras.get("memory") or {}
    memory_block = ""
    episodes = _filter_memory_for_chat(memory)
    if episodes:
        lines = []
        for ep in episodes[:5]:
            role = ep.get("role", "unknown")
            content = ep.get("content", "")
            lines.append(f"{role}: {content[:120]}")
        memory_block = "\n\n[Recent memory]\n" + "\n".join(lines)



    # 6) Call main ChatAgent
    reply = await chat_agent.run(
        message=augmented_message + memory_block,
        history=ctx.history,
        device=ctx.device,
        tools_used=tools_meta or None,
    )

    # 7) Surface verification issues if any
    if verification and not verification.get("ok", True):
        failed_names = ", ".join(verification.get("failed_tools") or [])
        reply = (
            reply.strip()
            + f"\n\n(Note: some tools failed internally: {failed_names}. "
              "I still returned what I could.)"
        )

    ctx.extras["final_reply"] = reply
    return reply


async def memory_node(ctx):
    return await memory_node_agent.run(ctx)


# ----------------------
# GRAPH CONSTRUCTION
# ----------------------

def build_cypher_graph() -> AgentGraph:
    """
    Construct the default Cypher Phase-4 graph.
    """
    graph = AgentGraph(name="cypher-core")

    graph.add_node(GraphNode("intent", intent_node))
    graph.add_node(GraphNode("entity", entity_node, requires=["intent"]))
    graph.add_node(GraphNode("safety", safety_node, requires=["entity"]))

    # Reasoning & arbitration depend on safety too
    graph.add_node(GraphNode("memory", memory_node, requires=["safety"]))
    graph.add_node(GraphNode("reasoning", reasoning_node, requires=["memory"]))

    graph.add_node(GraphNode("arbiter", arbiter_node, requires=["reasoning"]))

    graph.add_node(GraphNode("planner", planner_node, requires=["arbiter"]))
    graph.add_node(GraphNode("executor", executor_node, requires=["planner"]))
    graph.add_node(GraphNode("verifier", verifier_node, requires=["executor"]))

    graph.add_node(GraphNode("failure", failure_node, requires=["verifier"]))
    graph.add_node(GraphNode("chat", chat_node, requires=["failure"], allow_parallel=False))



    return graph
