import os
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt, JWTError
from dotenv import load_dotenv

# Load .env (root)
load_dotenv()

# Import routers AFTER dotenv
from cloud.api import routes_intent
from cloud.api import routes_nlu
from cloud.api.tts import router as tts_router

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
SECRET_KEY = os.environ.get("CY_SECRET", "change-this-for-prod")
ALGORITHM = "HS256"

app = FastAPI(title="Cypher API - Phase 1C")

# Routers
app.include_router(tts_router)
app.include_router(routes_intent.router)
app.include_router(routes_nlu.router)

# Device registry (simple Phase-1)
DEVICE_REGISTRY = {}


# -------------------------------------------------------------------
# MODELS
# -------------------------------------------------------------------
class DeviceRegister(BaseModel):
    device_id: str
    public_key: str | None = None


class TranscriptIn(BaseModel):
    device_id: str
    transcript: str
    metadata: dict | None = None


# -------------------------------------------------------------------
# TOKEN VERIFICATION
# -------------------------------------------------------------------
def verify_token(authorization: str | None = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid auth header")

    token = parts[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# -------------------------------------------------------------------
# ENDPOINTS
# -------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/v1/device/register")
def register_device(payload: DeviceRegister):
    DEVICE_REGISTRY[payload.device_id] = {"public_key": payload.public_key}

    expire = datetime.utcnow() + timedelta(hours=24)
    token = jwt.encode(
        {"sub": payload.device_id, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return {
        "device_id": payload.device_id,
        "status": "registered",
        "token": token,
    }


@app.post("/v1/transcript")
def receive_transcript(payload: TranscriptIn, device_id: str = Depends(verify_token)):
    """
    Phase-1C:
    - Transcript still echoed back
    - NLU handled in routes_nlu
    """
    return {
        "device_id": payload.device_id,
        "received_transcript": payload.transcript,
        "server_time": datetime.utcnow().isoformat(),
    }


@app.post("/v1/tts")
async def tts_endpoint(request: Request):
    """
    Placeholder for server-side TTS (Phase-2).
    """
    body = await request.json()
    text = body.get("text", "")
    return {
        "status": "ok",
        "note": "Edge client handles TTS locally in Phase-1",
        "echo": text,
    }
