import requests

API = "https://cypher-api-156682572778.asia-south1.run.app"


def register_device(device_id="cypher-edge"):
    res = requests.post(f"{API}/v1/device/register", json={"device_id": device_id})
    res.raise_for_status()
    return res.json()["access_token"]
