# edge/client_app/edge_client.py
"""
Edge client — Phase 1C (NLU + smarter intent routing)

Flow:
 - Wait for wake flag (edge/wake/wake.flag)
 - Record via VAD, transcribe with whisper.cpp
 - Send transcript to server NLU endpoint (/v1/nlu)
 - If NLU returns intent with sufficient confidence => use it
 - Else fallback to local heuristic routing (Phase-1 rules)
 - Post chosen intent to /v1/intent
 - Extract reply_text (various shapes supported) and request TTS (OpenAI) via client tts_client
 - Play TTS output
"""

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
API_BASE = os.getenv('CY_API', 'http://127.0.0.1:8000').rstrip('/')
NLU_ENDPOINT = os.getenv('CY_NLU_ENDPOINT', f'{API_BASE}/v1/nlu')
DEVICE_TOKEN = os.getenv('CY_DEVICE_TOKEN', '')
DEVICE_ID = os.getenv('CY_DEVICE_ID', 'edge-device-001')
NLU_CONF_THRESHOLD = float(os.getenv('CY_NLU_CONF_THRESHOLD', '0.55'))  # accept NLU intent if >= this
TTS_VOICE = os.getenv('CY_TTS_VOICE', 'shimmer')  # default voice for Phase1C
REQUEST_TIMEOUT = int(os.getenv('CY_HTTP_TIMEOUT', '30'))

# ----------------------------
# API HELPERS
# ----------------------------
def _auth_headers():
    return {'Authorization': f'Bearer {DEVICE_TOKEN}'} if DEVICE_TOKEN else {}

def post_transcript(text):
    """Send raw transcript to the server."""
    headers = _auth_headers()
    payload = {'device_id': DEVICE_ID, 'transcript': text}
    try:
        r = requests.post(f'{API_BASE}/v1/transcript', json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        jr = r.json()
    except Exception as e:
        jr = {"error": "transcript_post_failed", "detail": str(e)}
    print("[SERVER transcript response] →", jr)
    return jr

def post_intent(intent, params=None):
    """Send routed intent to the server and RETURN JSON cleanly."""
    headers = _auth_headers()
    payload = {'device_id': DEVICE_ID, 'intent': intent, 'params': params or {}}
    try:
        r = requests.post(f'{API_BASE}/v1/intent', json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        jr = r.json()
    except Exception as e:
        jr = {"error": "intent_post_failed", "detail": str(e)}
    print("[SERVER intent response] →", jr)
    return jr

def call_nlu(transcript: str):
    """
    Call server-side NLU endpoint. Expect response like:
    {
      "intent": "search_flights",
      "params": {"origin":"BLR", "destination":"DEL"},
      "confidence": 0.87,
      "reply_text": "I found flights..."
    }
    """
    headers = _auth_headers()
    payload = {'device_id': DEVICE_ID, 'transcript': transcript}
    try:
        r = requests.post(NLU_ENDPOINT, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        jr = r.json()
    except Exception as e:
        jr = {"error": "nlu_call_failed", "detail": str(e)}
    print("[NLU response] →", jr)
    return jr

# ----------------------------
# REPLY TEXT EXTRACTOR (for TTS)
# ----------------------------
def extract_reply_text(resp: dict) -> str | None:
    """
    Always extract a meaningful reply text from server response.
    Supports various Phase-1/1C patterns.
    """
    if not isinstance(resp, dict):
        return None

    # top-level explicit
    if "reply_text" in resp and isinstance(resp["reply_text"], str):
        return resp["reply_text"]

    # inside "result"
    result = resp.get("result", {})
    if isinstance(result, dict):
        if "reply_text" in result and isinstance(result["reply_text"], str):
            return result["reply_text"]
        if "reply" in result and isinstance(result["reply"], str):
            return result["reply"]
        if "summary" in result and isinstance(result["summary"], str):
            return result["summary"]

    # sometimes intent endpoint returns a short message
    if "message" in resp and isinstance(resp["message"], str):
        return resp["message"]

    # fallback: if intent present, produce a neutral reply
    if "intent" in resp:
        return f"Okay. Intent {resp['intent']} received."

    return None

# ----------------------------
# LOCAL HEURISTIC FALLBACK (Phase-1 rules)
# ----------------------------
def heuristic_route(transcript: str):
    lower = transcript.lower()
    if "flight" in lower or "flights" in lower:
        return "search_flights", {"origin": "BLR", "destination": "DEL"}
    if "eta" in lower or "reach" in lower:
        return "get_eta", {}
    if "pay" in lower or "payment" in lower:
        # extract an amount could be improved; use 100 as placeholder
        return "make_payment", {"amount": 100}
    # default query
    return "query", {"q": transcript}

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
                try:
                    os.remove("edge/wake/wake.flag")
                except OSError:
                    pass

                # STEP 1 — RECORD SPEECH
                ts = int(time.time())
                wav_path = f"edge/asr/recordings/record_{ts}.wav"
                record_until_silence(wav_path)

                # STEP 2 — TRANSCRIBE
                try:
                    transcript = transcribe_with_whispercpp(wav_path).strip()
                except Exception as e:
                    print("[EDGE ERROR] ASR transcription failed:", e)
                    transcript = ""

                print(f"[ASR] Transcript: {transcript}")

                if not transcript:
                    print("[EDGE] Empty transcript — skipping.")
                    continue

                # STEP 3 — POST RAW TRANSCRIPT (analytics / storage)
                post_transcript(transcript)

                # STEP 4 — CALL NLU (server)
                nlu_resp = call_nlu(transcript)

                chosen_intent = None
                chosen_params = None
                used_nlu = False

                # If NLU returned an intent and confidence, & it passes threshold -> accept
                if isinstance(nlu_resp, dict) and "intent" in nlu_resp:
                    conf = nlu_resp.get("confidence")
                    # If server doesn't return confidence, assume it's reliable; otherwise require threshold
                    if conf is None or (isinstance(conf, (int, float)) and conf >= NLU_CONF_THRESHOLD):
                        chosen_intent = nlu_resp.get("intent")
                        chosen_params = nlu_resp.get("params", {}) or {}
                        used_nlu = True
                        print(f"[EDGE] Using NLU intent='{chosen_intent}' (conf={conf})")
                    else:
                        print(f"[EDGE] NLU low confidence ({conf}); falling back to local heuristic")

                # STEP 5 — FALLBACK HEURISTIC IF NEEDED
                if not chosen_intent:
                    chosen_intent, chosen_params = heuristic_route(transcript)
                    print(f"[EDGE] Heuristic chose intent='{chosen_intent}' params={chosen_params}")

                # STEP 6 — POST INTENT TO SERVER
                server_resp = post_intent(chosen_intent, chosen_params)

                # STEP 7 — Pick reply text to TTS
                # prefer NLU reply_text if present, else server response text
                reply_text = None
                if used_nlu:
                    # try to use nlu reply_text first
                    reply_text = extract_reply_text(nlu_resp)
                if not reply_text:
                    reply_text = extract_reply_text(server_resp)
                print("[EDGE] reply_text =", reply_text)

                # STEP 8 — TTS and play
                if reply_text:
                    try:
                        out_path = "edge/tts/tts_reply.wav"
                        wav_out = fetch_tts_and_save(reply_text, out_path=out_path, voice=TTS_VOICE)
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
