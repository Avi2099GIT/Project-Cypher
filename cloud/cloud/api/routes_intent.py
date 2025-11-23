# cloud/api/routes_intent.py

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from cloud.orchestrator.runner import LangGraphRunner

router = APIRouter(prefix="/v1")

# -----------------------------
# Local verify_token function
# -----------------------------
def verify_token(authorization: str | None = Header(None)):
    """
    Token verification is duplicated here to avoid circular imports.
    """
    import os
    from jose import jwt, JWTError

    SECRET_KEY = os.environ.get("CY_SECRET", "change-this-for-prod")
    ALGORITHM = "HS256"

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


# -----------------------------
# Request Models
# -----------------------------
class IntentIn(BaseModel):
    device_id: str
    intent: str
    params: dict | None = None


# -----------------------------
# Intent Endpoint
# -----------------------------
@router.post("/intent")
def handle_intent(payload: IntentIn, device_id: str = Depends(verify_token)):
    runner = LangGraphRunner()
    result = runner.run_intent(payload.intent, payload.params or {})
    return {
        "device_id": payload.device_id,
        "intent": payload.intent,
        "result": result
    }
