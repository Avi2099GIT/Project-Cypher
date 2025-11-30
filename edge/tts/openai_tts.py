import os
import requests
from dotenv import load_dotenv

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_KEY:
    raise SystemExit("❌ OPENAI_API_KEY not set in env")


def synthesize_to_file(text, out_path="tts_output.mp3"):
    url = "https://api.openai.com/v1/audio/speech"

    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini-tts",
        "input": text,
        "voice": "marin",
        "format": "wav"
    }

    r = requests.post(url, headers=headers, json=payload)

    # Debug safety net
    print("TTS status:", r.status_code)
    print("TTS Content-Type:", r.headers.get("Content-Type"))
    print("Content-Type:", r.headers.get("Content-Type"))

    if r.status_code != 200:
        raise RuntimeError("❌ TTS failed: " + r.text)

    # Save audio correctly
    with open(out_path, "wb") as f:
        f.write(r.content)

    print("✅ Audio written:", out_path)
    return out_path
