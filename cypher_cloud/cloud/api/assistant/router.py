# cloud/api/assistant/router.py
from __future__ import annotations

from typing import Dict, Any, List
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .agents_dir.brain import CypherBrain
from .memory import memory_service

router = APIRouter(prefix="/v1/assistant", tags=["Assistant"])

# Create one shared Cypher brain instance (correct)
brain = CypherBrain()


# -------------------------------------------------------------------
# Request / Response models
# -------------------------------------------------------------------

class AssistantQuery(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply_text: str
    tools_used: List[Dict[str, Any]] = Field(default_factory=list)
    memory_used: Dict[str, Any] = Field(default_factory=dict)


# -------------------------------------------------------------------
# MAIN ENDPOINT (MULTI-AGENT PIPELINE)
# -------------------------------------------------------------------

@router.post("/query", response_model=AssistantResponse)
async def assistant_query(payload: AssistantQuery):

    # Identify device (later replace with auth / device registry)
    device: Dict[str, Any] = {"device_id": "local-dev"}

    # Retrieve short-term memory history
    history: List[Dict[str, Any]] = memory_service.get_short_term_history(device)

    # Shared context for all agents
    ctx: Dict[str, Any] = {
        "device": device,
        "history": history,
        "message": payload.message,
    }

    # 🔹 Run Multi-Agent Brain
    reply_text, tools_used = await brain.process(payload.message, ctx)

    # 🔹 Store conversation turn in memory engine
    await memory_service.record_interaction(
        device=device,
        user_message=payload.message,
        reply_text=str(reply_text),
        tools_used=tools_used,
    )

    # 🔹 Snapshot memory (for UI / debug / Streamlit)
    memory_view = memory_service.get_memory_view(device)

    return AssistantResponse(
        reply_text=str(reply_text),
        tools_used=tools_used,
        memory_used=memory_view,
    )
