# cloud/api/main.py
import os
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from .tts import router as tts_router
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()  # load root .env by default

SECRET_KEY = os.environ.get('CY_SECRET', 'change-this-for-prod')
ALGORITHM = 'HS256'

app = FastAPI(title='Cypher API (Phase0+1 REAL)')
app.include_router(tts_router)

# include routes_intent router (safe because routes_intent no longer imports main)
from . import routes_intent
app.include_router(routes_intent.router)

DEVICE_REGISTRY = {}

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

class TranscriptIn(BaseModel):
    device_id: str
    transcript: str
    metadata: dict | None = None

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

@app.post('/v1/transcript')
def receive_transcript(payload: TranscriptIn, device_id: str = Depends(verify_token)):
    # Persist/forward in Phase-2. For Phase-1 return echo.
    return {'device_id': payload.device_id, 'received_transcript': payload.transcript, 'server_time': datetime.utcnow().isoformat()}

# Keep TTS endpoint as a placeholder (server-side TTS in Phase2)
@app.post('/v1/tts')
async def tts_endpoint(request: Request):
    data = await request.json()
    text = data.get('text','')
    return {'status':'ok','note':'clients should call OpenAI TTS directly in Phase1'}
