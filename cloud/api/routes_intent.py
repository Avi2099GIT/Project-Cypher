import os
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from jose import jwt, JWTError

from . import intent_handler  # Phase-1B logic stays unchanged

router = APIRouter(prefix="/v1")

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
SECRET_KEY = os.environ.get("CY_SECRET", "change-this-for-prod")
ALGORITHM = "HS256"


# -------------------------------------------------------------------
# MODELS
# -------------------------------------------------------------------
class IntentIn(BaseModel):
    device_id: str
    intent: str
    params: dict | None = None


# -------------------------------------------------------------------
# TOKEN VALIDATION (LOCAL COPY)
# -------------------------------------------------------------------
def verify_token_local(authorization: str | None = Header(None)):
    """
    Local version of verify_token to avoid circular imports.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    token = parts[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# -------------------------------------------------------------------
# INTENT ENDPOINT
# -------------------------------------------------------------------
@router.post("/intent")
def handle_intent(payload: IntentIn, device_id: str = Depends(verify_token_local)):
    """
    Phase-1C:
    - Now called from routes_nlu AFTER LLM classification
    - Still supports direct calls for debugging.
    """
    resp = intent_handler.handle_intent(
        device_id=payload.device_id,
        intent=payload.intent,
        params=payload.params or {},
    )

    return resp
