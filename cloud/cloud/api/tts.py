# cloud/api/tts.py
"""
Phase-1B: Server does NOT generate TTS.
The TTS endpoint exists only so the client has a valid route.
"""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1")


@router.post("/tts")
async def tts_stub(request: Request):
    """
    Phase 1B:
    - Client handles TTS locally.
    - Server should NEVER require OPENAI_API_KEY.
    - Always return a simple JSON response.
    """
    data = await request.json()
    text = data.get("text", "")

    return {
        "status": "ok",
        "note": "Server-side TTS disabled in Phase 1B. Client must call OpenAI TTS directly.",
        "echo": text
    }
