from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException

from cloud.api.assistant.orchestrator.tracer import tracer  # adapt to your actual tracer object

router = APIRouter(prefix="/v1/traces", tags=["Traces"])


@router.get("/", response_model=List[Dict[str, Any]])
async def list_traces() -> List[Dict[str, Any]]:
    """
    Return lightweight summaries of recent traces.
    """
    summaries = []
    for t in tracer.list_traces():  # you implement list_traces() → iterable of trace objects/dicts
        summaries.append(
            {
                "trace_id": t["trace_id"],
                "created_at": t.get("created_at"),
                "message": t.get("message"),
                "mode": (t.get("decision") or {}).get("mode"),
                "status": t.get("status", "UNKNOWN"),
                "total_latency_ms": t.get("total_latency_ms"),
            }
        )
    return summaries


@router.get("/{trace_id}", response_model=Dict[str, Any])
async def get_trace(trace_id: str) -> Dict[str, Any]:
    """
    Return full detail for a single trace.
    """
    trace = tracer.get_trace(trace_id)  # implement get_trace(trace_id) → dict or None
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace
