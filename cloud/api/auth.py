# cloud/api/auth.py
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import jwt, JWTError
from fastapi import HTTPException, Header, Depends

load_dotenv()

SECRET_KEY = os.getenv("CY_SECRET", "change-this-for-prod")
ALGORITHM = os.getenv("CY_ALGORITHM", "HS256")
TOKEN_EXPIRE_HOURS = int(os.getenv("CY_TOKEN_EXPIRE_HOURS", "24"))

def create_device_token(device_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    token = jwt.encode({"sub": device_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    return token

def verify_token(authorization: str | None = Header(None)) -> str:
    """
    FastAPI dependency — returns device_id (sub) or raises HTTPException 401.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    token = parts[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        device_id = payload.get("sub")
        if not device_id:
            raise HTTPException(status_code=401, detail="Invalid token (no sub)")
        return device_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
