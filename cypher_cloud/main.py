# cypher_cloud/main.py
from dotenv import load_dotenv
load_dotenv()
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
