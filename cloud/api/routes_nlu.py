# cloud/api/routes_nlu.py
import os
import re
import json
import requests
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any
from .auth import verify_token
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_NLU_MODEL", "gpt-4o-mini")  # changeable

router = APIRouter(prefix="/v1", tags=["nlu"])

class NLUIn(BaseModel):
    device_id: str
    transcript: str
    metadata: dict | None = None

class NLUOut(BaseModel):
    device_id: str
    intent: str
    entities: Dict[str, Any] = {}
    confidence: float = 0.0
    raw: dict | None = None

def rule_based_nlu(text: str) -> Dict[str, Any]:
    """
    Lightweight rule-based NLU for Phase1C fallback.
    Detects simple intents + basic entities (origin/destination/amount).
    """
    t = text.lower()
    # default
    intent = "query"
    entities = {}
    confidence = 0.6

    # flights
    if "flight" in t or "flights" in t or "book" in t:
        intent = "search_flights"
        # origin/destination heuristics: words like from <X> to <Y>
        m = re.search(r"from\s+([a-zA-Z\s]+?)\s+(?:to|for)\s+([a-zA-Z\s]+)", t)
        if m:
            entities["origin"] = m.group(1).strip().title()
            entities["destination"] = m.group(2).strip().title()
            confidence = 0.9
        else:
            # try "to <Y>" only
            m2 = re.search(r"to\s+([a-zA-Z\s]+)", t)
            if m2:
                entities["destination"] = m2.group(1).strip().title()
                confidence = 0.75

    # ETA
    elif "eta" in t or "when will" in t or "reach" in t:
        intent = "get_eta"
        confidence = 0.8

    # payment
    elif "pay" in t or "payment" in t or re.search(r"\b(?:rupees|rs|₹|\$)\b", t):
        intent = "make_payment"
        # try extract amount
        m = re.search(r"(\d+)(?:\s*(?:rupees|rs|₹|\$))?", t)
        if m:
            entities["amount"] = int(m.group(1))
            confidence = 0.85
        else:
            confidence = 0.6

    else:
        intent = "query"
        confidence = 0.5

    return {"intent": intent, "entities": entities, "confidence": confidence}

def call_openai_nlu(transcript: str) -> dict:
    """
    Use OpenAI to extract intent & entities as JSON.
    This is a best-effort prompt; keep small and deterministic.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    system = (
        "You are a strict JSON NLU extractor. Given a user's transcript, "
        "return a JSON object with keys: intent (one of search_flights, get_eta, make_payment, query), "
        "entities (object), and confidence (0.0-1.0). Do not return any extra text."
    )
    user = (
        f"Transcript: ```{transcript}```\n\n"
        "Return JSON only. Example:\n"
        "{\"intent\":\"search_flights\",\"entities\":{\"origin\":\"Bangalore\",\"destination\":\"Dubai\"},\"confidence\":0.92}\n"
    )
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.0,
        "max_tokens": 200,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI NLU failed: {r.status_code} {r.text}")
    jr = r.json()
    # find assistant content
    try:
        content = jr["choices"][0]["message"]["content"]
        # attempt to parse JSON out of it
        parsed = json.loads(content.strip())
        return {"intent": parsed.get("intent"), "entities": parsed.get("entities", {}), "confidence": float(parsed.get("confidence", 0.0)), "raw": parsed}
    except Exception as e:
        # If parsing fails, raise for now
        raise RuntimeError("OpenAI NLU returned non-JSON or parsing failed: " + str(e))

@router.post("/nlu", response_model=NLUOut)
def nlu_endpoint(payload: NLUIn, device_id: str = Depends(verify_token)):
    """
    Accepts: { device_id, transcript, metadata? }
    Returns: { device_id, intent, entities, confidence, raw? }
    """
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Empty transcript")

    # Prefer OpenAI if available
    if OPENAI_API_KEY:
        try:
            out = call_openai_nlu(transcript)
            return {"device_id": payload.device_id, "intent": out["intent"] or "query", "entities": out.get("entities", {}), "confidence": out.get("confidence", 0.0), "raw": out.get("raw")}
        except Exception as e:
            # Log but fall back to rules
            print("[NLU] OpenAI NLU failed, falling back to rule-based. Error:", e)

    # fallback
    out = rule_based_nlu(transcript)
    return {"device_id": payload.device_id, "intent": out["intent"], "entities": out.get("entities", {}), "confidence": out.get("confidence", 0.0), "raw": None}
