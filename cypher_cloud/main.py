# cypher_cloud/main.py
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from cloud.api.assistant.router import router as assistant_router

app = FastAPI(title="Cypher AI Core", version="3.0")

# Register API routes
app.include_router(assistant_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "cypher-cloud"}
