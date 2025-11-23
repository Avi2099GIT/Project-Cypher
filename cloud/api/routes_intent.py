# cloud/api/routes_intent.py
import os
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from jose import jwt, JWTError
from datetime import datetime, timedelta

from . import intent_handler

router = APIRouter(prefix="/v1")

SECRET_KEY = os.environ.get('CY_SECRET', 'change-this-for-prod')
ALGORITHM = 'HS256'

class IntentIn(BaseModel):
    device_id: str
    intent: str
    params: dict | None = None

def verify_token_local(authorization: str | None = Header(None)):
    """
    Local copy of token verification to avoid circular imports.
    Returns device_id (sub) if valid, otherwise raises 401.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail='Missing Authorization header')
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise HTTPException(status_code=401, detail='Invalid auth header')
    token = parts[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get('sub')
    except JWTError:
        raise HTTPException(status_code=401, detail='Invalid token')

@router.post("/intent")
def handle_intent(payload: IntentIn, device_id: str = Depends(verify_token_local)):
    """
    Entrypoint for intents. Uses intent_handler to compute result and reply_text.
    """
    resp = intent_handler.handle_intent(device_id=payload.device_id, intent=payload.intent, params=payload.params or {})
    return resp
