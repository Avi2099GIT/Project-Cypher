import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Force Reload Trigger 2025-12-18 00:45
import os
from pathlib import Path
from dotenv import load_dotenv
# Load from parent directory (cypher_edge_runtime/.env)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
from fastapi import FastAPI
from cloud.api.assistant.router import router as assistant_router

app = FastAPI(title="Cypher AI Core", version="3.0")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(assistant_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "cypher-cloud"}