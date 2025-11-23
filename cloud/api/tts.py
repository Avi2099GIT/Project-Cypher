# cloud/api/tts.py
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[cloud.api.tts] WARNING: OPENAI_API_KEY not set. TTS endpoints will be disabled.")

class TTSIn(BaseModel):
    text: str
    voice: str | None = None

@router.post("/v1/server_tts")
async def server_tts(payload: TTSIn):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=501, detail="Server-side TTS not configured (OPENAI_API_KEY missing). Use client-side TTS in Phase1.")
    # Phase-1: simply echo note. Full server-side TTS implemented in Phase-2.
    return {"status":"ok", "note":"Server-side TTS disabled in Phase1; use client TTS."}
