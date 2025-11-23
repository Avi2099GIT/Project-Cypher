import os
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from .tts import router as tts_router
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt, JWTError

from cloud.api import routes_intent
from cloud.api.intent_handler import handle_intent   # NEW ← Phase 1B

from dotenv import load_dotenv
load_dotenv()  # loads .env in project root or cloud/api/.env

SECRET_KEY = os.environ.get('CY_SECRET','change-this-for-prod')
ALGORITHM = 'HS256'

app = FastAPI(title='Cypher API (Phase1B)')
app.include_router(tts_router)
app.include_router(routes_intent.router)

DEVICE_REGISTRY = {}

# ---------------------------
# DEVICE REGISTRATION
# ---------------------------

class DeviceRegister(BaseModel):
    device_id: str
    public_key: str | None = None

@app.get('/health')
def health():
    return {'status':'ok', 'time': datetime.utcnow().isoformat()}

@app.post('/v1/device/register')
def register_device(payload: DeviceRegister):
    DEVICE_REGISTRY[payload.device_id] = {'public_key': payload.public_key}
    expire = datetime.utcnow() + timedelta(hours=24)
    token = jwt.encode({'sub': payload.device_id, 'exp': expire}, SECRET_KEY, algorithm=ALGORITHM)
    return {'device_id': payload.device_id, 'status': 'registered', 'token': token}


# ---------------------------
# TOKEN VERIFICATION
# ---------------------------

def verify_token(authorization: str | None = Header(None)):
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


# ---------------------------
# TRANSCRIPT ENDPOINT
# ---------------------------

class TranscriptIn(BaseModel):
    device_id: str
    transcript: str
    metadata: dict | None = None

@app.post('/v1/transcript')
def receive_transcript(payload: TranscriptIn, device_id: str = Depends(verify_token)):
    return {
        'device_id': payload.device_id,
        'received_transcript': payload.transcript,
        'server_time': datetime.utcnow().isoformat()
    }


# ---------------------------
# INTENT ENDPOINT — Phase 1B
# ---------------------------

class IntentIn(BaseModel):
    device_id: str
    intent: str
    params: dict | None = None

@app.post('/v1/intent')
def handle_intent_phase1b(payload: IntentIn, device_id: str = Depends(verify_token)):
    
    # Call Phase 1B handler instead of LangGraphRunner
    handler_output = handle_intent(payload.intent, payload.params or {})
    
    return {
        'device_id': payload.device_id,
        'intent': payload.intent,
        'result': handler_output.get('result'),
        'reply_text': handler_output.get('reply_text'),
        'server_time': datetime.utcnow().isoformat()
    }


# ---------------------------
# SERVER-SIDE TTS (for future phases)
# ---------------------------

@app.post('/v1/tts')
async def tts_endpoint(request: Request):
    data = await request.json()
    text = data.get('text','')
    return {
        'status':'ok',
        'note':'clients should call OpenAI TTS directly in Phase1B'
    }
