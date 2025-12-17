# from __future__ import annotations

# from typing import Dict, Any, List
# from fastapi import APIRouter, Query
# from pydantic import BaseModel, Field
# from cloud.api.assistant.agents_dir.reasoning_agent import ReasoningAgent
# from .agents_dir.brain import CypherBrain
# from .memory import memory_service
# #from .trace_router import router as trace_router
# from cloud.api.assistant.mcp.metrics import snapshot_metrics
# router = APIRouter(prefix="/v1/assistant", tags=["Assistant"])

# # Create one shared Cypher brain instance
# brain = CypherBrain()

# from cloud.api.assistant.orchestrator.tracer import tracer


# @router.get("/debug/trace")
# def get_trace():
#     return {
#         "events": tracer.timeline(),
#         "summary": tracer.summary(),
#         "slowest": tracer.slowest_nodes(),
#     }

# # -------------------------------------------------------------------
# # Request / Response models
# # -------------------------------------------------------------------


# class AssistantQuery(BaseModel):
#     message: str


# class AssistantResponse(BaseModel):
#     reply_text: str
#     tools_used: List[Dict[str, Any]] = Field(default_factory=list)
#     memory_used: Dict[str, Any] = Field(default_factory=dict)


# # -------------------------------------------------------------------
# # MAIN ENDPOINT (MULTI-AGENT PIPELINE)
# # -------------------------------------------------------------------

# #router.include_router(trace_router)
# @router.post("/query", response_model=AssistantResponse)
# async def assistant_query(payload: AssistantQuery):

#     # Identify device (placeholder until auth/device registry is added)
#     device: Dict[str, Any] = {"device_id": "local-dev"}

#     # Retrieve episodic memory (short-term context)
#     history: List[Dict[str, Any]] = memory_service.get_recent_episodes(
#         device=device,
#         limit=10,
#     )

#     if not history:
#         history = []

#     # Shared context for Cypher brain
#     ctx: Dict[str, Any] = {
#         "device": device,
#         "history": history,
#         "message": payload.message,
#     }

#     # --------------------------------------------------------
#     # Run Cypher Core Brain
#     # --------------------------------------------------------
#     #tracer.clear()
#     ctx["trace_id"] = tracer.new_trace()
#     reply_text, tools_used = await brain.process(payload.message, ctx)


#     trace_id = ctx.get("trace_id")
#     if trace_id:
#         tracer.attach_context(trace_id, ctx)


#     # --------------------------------------------------------
#     # Store memory episodes (Memory V2)
#     # --------------------------------------------------------
#     try:
#         memory_service.store_episode(
#             device=device,
#             role="user",
#             content=payload.message,
#             meta={"source": "api", "trace_id": ctx["trace_id"]},
#         )

#         memory_service.store_episode(
#             device=device,
#             role="assistant",
#             content=reply_text,
#             meta={"source": "api", "trace_id": ctx["trace_id"]},
#         )

#     except Exception:
#         import logging
#         logging.exception("Failed to store memory episode")


#     # --------------------------------------------------------
#     # Snapshot memory (for UI / debug tools)
#     # --------------------------------------------------------
#     try:
#         memory_view = {
#             "recent_episodes": ReasoningAgent()._filter_memory_episodes(
#                 {"recent_episodes": memory_service.get_recent_episodes(device, limit=10)}
#             )
#         }

#     except Exception:
#         memory_view = {}

#     return AssistantResponse(
#         reply_text=str(reply_text),
#         tools_used=tools_used,
#         memory_used=memory_view,
#     )


# #from cloud.api.assistant.orchestrator.tracer import tracer

# # @router.get("/v1/assistant/debug/trace")
# # def get_trace():
# #     return {
# #         "events": tracer.timeline(),
# #         "summary": tracer.summary(),
# #         "slowest": tracer.slowest_nodes(),
# #     }


# @router.get("/debug/plan")
# async def debug_plan(trace_id: str | None = None):
#     """
#     Inspect the planner V2 decision and the chosen execution plan
#     for a given trace. If trace_id is not provided, the latest trace
#     from the tracer timeline is used.
#     """
#     # 1) Get timeline
#     events = tracer.timeline()
#     if not events:
#         return {"error": "No trace data yet"}

#     # 2) Use latest trace if none provided
#     if not trace_id:
#         trace_id = events[-1]["trace_id"]

#     # 3) Look up context (ExecutionContext) for this trace
#     ctx = tracer.get_context(trace_id)
#     if ctx is None:
#         return {"error": f"No context found for trace_id={trace_id}"}

#     # ctx is expected to be an ExecutionContext with .extras
#     extras = getattr(ctx, "extras", {}) or {}

#     # 4) Pull plan info out of extras
#     plan_obj = extras.get("execution_plan")
#     plan_steps = extras.get("plan") or []
#     plan_debug = extras.get("plan_debug") or {}

#     if plan_obj is None:
#         return {"error": "No plan attached to this trace"}

#     explanation = getattr(plan_obj, "explanation", None)
#     score = getattr(plan_obj, "score_breakdown", {})
#     rejected = getattr(plan_obj, "rejected", [])

#     # 5) 🔎 Arbiter info
#     #    First try annotations (EPIC #1 trace annotations),
#     #    then fall back to the decision stored in extras.
#     annotations = tracer.annotations_for(trace_id)
#     arbiter_info = None
#     if isinstance(annotations, dict):
#         arbiter_info = annotations.get("arbiter")

#     if arbiter_info is None:
#         # Fallback: arbiter decision stored by the graph in extras["decision"]
#         arbiter_info = extras.get("decision")

#     return {
#         "trace_id": trace_id,
#         "plan": {
#             "explanation": explanation,
#             "score": score,
#             "steps": plan_steps,
#             "rejected": rejected,
#         },
#         "arbiter": arbiter_info,
#         "debug": plan_debug,
#     }

# @router.get("/debug/metrics")
# def metrics():
#     return tracer.metrics()


# @router.get("/debug/memory")
# def debug_memory(trace_id: str = Query(...)):
#     """
#     Inspect all memory interactions related to a trace.
#     """
#     return memory_service.inspect_trace(trace_id)


# @router.get("/debug/trace/annotations")
# async def trace_annotations(trace_id: str | None = None):
#     """
#     Get annotations for a given trace-id, or all annotations if trace_id is omitted.
#     """
#     if trace_id:
#         return {
#             "trace_id": trace_id,
#             "annotations": tracer.annotations_for(trace_id),
#         }
#     return {
#         "annotations": tracer.all_annotations(),
#     }


# @router.get("/debug/trace/heatmap")
# def trace_heatmap():
#     return tracer.heatmap()

# @router.get("/debug/trace/slow")
# def trace_slow():
#     return tracer.slow_nodes()

# @router.get("/debug/trace/failures")
# def trace_failures():
#     return tracer.failure_map()

# @router.get("/debug/trace/{trace_id}")
# def trace_each(trace_id: str):
#     return tracer.trace_by_id(trace_id)


# @router.get("/debug/mcp")
# def mcp_status():
#     """
#     Returns a snapshot of MCP client metrics.
#     """
#     return snapshot_metrics()


from __future__ import annotations

from typing import Dict, Any, List
import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from cloud.api.assistant.agents_dir.reasoning_agent import ReasoningAgent
from cloud.api.assistant.agents_dir.brain import CypherBrain
from cloud.api.assistant.memory import memory_service
from cloud.api.assistant.orchestrator.tracer import tracer
from cloud.api.assistant.mcp.metrics import snapshot_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/assistant", tags=["Assistant"])

# ---------------------------------------------------------
# SHARED BRAIN INSTANCE
# ---------------------------------------------------------

brain = CypherBrain()

# ---------------------------------------------------------
# REQUEST / RESPONSE MODELS
# ---------------------------------------------------------


class AssistantQuery(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply_text: str
    tools_used: List[Dict[str, Any]] = Field(default_factory=list)
    memory_used: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------

def _filter_memory_for_ui(episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    UI-safe memory filtering.
    This mirrors ReasoningAgent behavior WITHOUT calling private methods.
    """
    filtered = []

    for ep in episodes or []:
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


def _get_tracer_extras(trace_id: str) -> Dict[str, Any]:
    """
    Safely extract tracer extras without assuming internal tracer types.
    """
    ctx = tracer.get_context(trace_id)
    if ctx is None:
        return {}

    # ExecutionContext case
    if hasattr(ctx, "extras") and isinstance(ctx.extras, dict):
        return ctx.extras

    # Dict fallback (defensive)
    if isinstance(ctx, dict):
        return ctx.get("extras", {}) or {}

    return {}


# ---------------------------------------------------------
# MAIN ASSISTANT ENDPOINT
# ---------------------------------------------------------

@router.post("/query", response_model=AssistantResponse)
async def assistant_query(payload: AssistantQuery):
    # Identify device (auth/device registry comes later)
    device: Dict[str, Any] = {"device_id": "local-dev"}

    # Retrieve recent memory
    history = memory_service.get_recent_episodes(
        device=device,
        limit=10,
    ) or []

    # Shared execution context
    ctx: Dict[str, Any] = {
        "device": device,
        "history": history,
        "message": payload.message,
    }

    # -----------------------------------------------------
    # TRACE START
    # -----------------------------------------------------

    ctx["trace_id"] = tracer.new_trace()

    # -----------------------------------------------------
    # RUN CYPHER CORE
    # -----------------------------------------------------

    reply_text, tools_used = await brain.process(payload.message, ctx)

    trace_id = ctx.get("trace_id")
    if trace_id:
        tracer.attach_context(trace_id, ctx)

    # -----------------------------------------------------
    # MEMORY WRITEBACK
    # -----------------------------------------------------

    try:
        memory_service.store_episode(
            device=device,
            role="user",
            content=payload.message,
            meta={"source": "api", "trace_id": trace_id},
        )

        memory_service.store_episode(
            device=device,
            role="assistant",
            content=reply_text,
            meta={"source": "api", "trace_id": trace_id},
        )

    except Exception:
        logger.exception("Failed to store memory episode")

    # -----------------------------------------------------
    # MEMORY SNAPSHOT (UI / DEBUG)
    # -----------------------------------------------------

    try:
        recent = memory_service.get_recent_episodes(device, limit=10)
        memory_view = {
            "recent_episodes": _filter_memory_for_ui(recent)
        }
    except Exception:
        memory_view = {}

    return AssistantResponse(
        reply_text=str(reply_text),
        tools_used=tools_used,
        memory_used=memory_view,
    )


# ---------------------------------------------------------
# DEBUG / INSPECTION ENDPOINTS
# ---------------------------------------------------------

@router.get("/debug/trace")
def debug_trace():
    return {
        "events": tracer.timeline(),
        "summary": tracer.summary(),
        "slowest": tracer.slowest_nodes(),
    }


@router.get("/debug/plan")
async def debug_plan(trace_id: str | None = None):
    events = tracer.timeline()
    if not events:
        return {"error": "No trace data yet"}

    if not trace_id:
        trace_id = events[-1]["trace_id"]

    extras = _get_tracer_extras(trace_id)

    plan_obj = extras.get("execution_plan")
    plan_steps = extras.get("plan") or []
    plan_debug = extras.get("plan_debug") or {}

    if plan_obj is None:
        return {"error": "No plan attached to this trace"}

    annotations = tracer.annotations_for(trace_id)
    arbiter_info = None
    if isinstance(annotations, dict):
        arbiter_info = annotations.get("arbiter")
    if arbiter_info is None:
        arbiter_info = extras.get("decision")

    return {
        "trace_id": trace_id,
        "plan": {
            "explanation": getattr(plan_obj, "explanation", None),
            "score": getattr(plan_obj, "score_breakdown", {}),
            "steps": plan_steps,
            "rejected": getattr(plan_obj, "rejected", []),
        },
        "arbiter": arbiter_info,
        "debug": plan_debug,
    }


@router.get("/debug/metrics")
def debug_metrics():
    return tracer.metrics()


@router.get("/debug/memory")
def debug_memory(trace_id: str = Query(...)):
    return memory_service.inspect_trace(trace_id)


@router.get("/debug/trace/annotations")
async def trace_annotations(trace_id: str | None = None):
    if trace_id:
        return {
            "trace_id": trace_id,
            "annotations": tracer.annotations_for(trace_id),
        }
    return {"annotations": tracer.all_annotations()}


@router.get("/debug/trace/heatmap")
def trace_heatmap():
    return tracer.heatmap()


@router.get("/debug/trace/slow")
def trace_slow():
    return tracer.slow_nodes()


@router.get("/debug/trace/failures")
def trace_failures():
    return tracer.failure_map()


@router.get("/debug/trace/{trace_id}")
def trace_each(trace_id: str):
    return tracer.trace_by_id(trace_id)


@router.get("/debug/mcp")
def mcp_status():
    return snapshot_metrics()
