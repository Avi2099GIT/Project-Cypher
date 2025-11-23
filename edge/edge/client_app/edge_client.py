import os
import time
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# ----------------------------
# FORCE LOAD ROOT .env
# ----------------------------
ROOT_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(dotenv_path=ROOT_ENV, override=True)

print("[DEBUG] Loaded .env from:", ROOT_ENV)
print("WHISPER_CPP_BIN =", os.getenv("WHISPER_CPP_BIN"))
print("WHISPER_MODEL_PATH =", os.getenv("WHISPER_MODEL_PATH"))

# -----------------------------------------------------
# FIX IMPORT PATH FOR edge/*
# -----------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Local imports AFTER sys.path fix
from edge.asr.asr_recorder import record_until_silence
from edge.asr.asr_whisper import transcribe_with_whispercpp
from edge.client_app.tts_client import fetch_tts_and_save, play_wav_sync

# Reload env once more (safety)
load_dotenv(dotenv_path=ROOT_ENV)

# ----------------------------
# CONFIG
# ----------------------------
API_BASE = os.getenv('CY_API', 'http://127.0.0.1:8000')
DEVICE_TOKEN = os.getenv('CY_DEVICE_TOKEN', '')
DEVICE_ID = os.getenv('CY_DEVICE_ID', 'edge-device-001')

# ----------------------------
# API HELPERS
# ----------------------------
def post_transcript(text):
    """Send raw transcript to the server."""
    headers = {'Authorization': f'Bearer {DEVICE_TOKEN}'} if DEVICE_TOKEN else {}
    payload = {'device_id': DEVICE_ID, 'transcript': text}

    r = requests.post(f'{API_BASE}/v1/transcript', json=payload, headers=headers, timeout=30)

    try:
        jr = r.json()
    except:
        jr = {"error": "invalid_json", "raw": r.text}

    print("[SERVER transcript response] →", jr)
    return jr


def post_intent(intent, params=None):
    """Send routed intent to the server and RETURN JSON cleanly."""
    headers = {'Authorization': f'Bearer {DEVICE_TOKEN}'} if DEVICE_TOKEN else {}
    payload = {'device_id': DEVICE_ID, 'intent': intent, 'params': params or {}}

    r = requests.post(f'{API_BASE}/v1/intent', json=payload, headers=headers, timeout=30)

    try:
        jr = r.json()
    except:
        jr = {"error": "invalid_json", "raw": r.text}

    print("[SERVER intent response] →", jr)
    return jr


# ----------------------------
# REPLY TEXT EXTRACTOR (for TTS)
# ----------------------------
def extract_reply_text(resp: dict) -> str:
    """
    Always extract a meaningful reply text from server response.
    Supports all Phase-1 patterns.
    """

    if not isinstance(resp, dict):
        return None

    # Preferred explicit field
    if "reply_text" in resp:
        return resp["reply_text"]

    # Sometimes inside "result"
    result = resp.get("result", {})
    if isinstance(result, dict):

        if "reply_text" in result:
            return result["reply_text"]

        if "reply" in result:  # generic
            return result["reply"]

        if "summary" in result:  # fallback
            return result["summary"]

    # FINAL fallback
    if "intent" in resp:
        return f"Okay. Intent {resp['intent']} received."

    return None


# ----------------------------
# MAIN LOOP
# ----------------------------
def main_loop():
    print("Edge Client running. Waiting for wake flags...")

    while True:
        try:
            # Wake word detected
            if os.path.exists("edge/wake/wake.flag"):

                print("\n[EDGE] Wake detected — starting ASR capture...")
                os.remove("edge/wake/wake.flag")

                # ----------------------------
                # STEP 1 — RECORD SPEECH
                # ----------------------------
                ts = int(time.time())
                wav_path = f"edge/asr/recordings/record_{ts}.wav"
                record_until_silence(wav_path)

                # ----------------------------
                # STEP 2 — TRANSCRIBE
                # ----------------------------
                transcript = transcribe_with_whispercpp(wav_path).strip()
                print(f"[ASR] Transcript: {transcript}")

                if not transcript:
                    print("[EDGE] Empty transcript — skipping.")
                    continue

                # ----------------------------
                # STEP 3 — POST TRANSCRIPT
                # ----------------------------
                post_transcript(transcript)

                # ----------------------------
                # STEP 4 — ROUTE INTENT (Phase-1)
                # ----------------------------
                lower = transcript.lower()

                # NOTE: Phase-2 will replace this with NLU.
                if "flight" in lower or "flights" in lower:
                    # Still BLR→DEL for Phase-1B
                    server_resp = post_intent("search_flights", {"origin": "BLR", "destination": "DEL"})

                elif "eta" in lower or "reach" in lower:
                    server_resp = post_intent("get_eta", {})

                elif "pay" in lower or "payment" in lower:
                    server_resp = post_intent("make_payment", {"amount": 100})

                else:
                    server_resp = post_intent("query", {"q": transcript})

                # ----------------------------
                # STEP 5 — EXTRACT reply_text
                # ----------------------------
                reply_text = extract_reply_text(server_resp)
                print("[EDGE] reply_text =", reply_text)

                # ----------------------------
                # STEP 6 — TTS → PLAY VALE
                # ----------------------------
                if reply_text:
                    try:
                        wav_out = fetch_tts_and_save(reply_text, out_path="edge/tts/tts_reply.wav", voice="shimmer")
                        play_wav_sync(wav_out)
                    except Exception as e:
                        print("[EDGE TTS ERROR]", e)

                print("\n[EDGE] Completed. Await next wake word.\n")

            time.sleep(0.2)

        except KeyboardInterrupt:
            print("\n[EDGE] Stopping client.")
            break

        except Exception as e:
            print("[EDGE ERROR]", e)
            time.sleep(1)



if __name__ == "__main__":
    main_loop()
