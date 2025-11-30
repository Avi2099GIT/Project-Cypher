import requests
from edge.client_app.client.auth import register_device

API = "https://cypher-api-156682572778.asia-south1.run.app"
TOKEN = register_device()


def send_query(text, state):
    payload = {
        "message": text,
        "conversation_id": state.conversation_id
    }

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    r = requests.post(f"{API}/v1/assistant/query", json=payload, headers=headers)
    r.raise_for_status()

    data = r.json()
    return data["reply_text"]
