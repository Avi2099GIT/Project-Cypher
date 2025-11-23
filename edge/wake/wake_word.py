import os
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import pvporcupine
from dotenv import load_dotenv

# -------------------------------------------------------
# Load environment variables
# -------------------------------------------------------
load_dotenv()

PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "").strip()
PORCUPINE_KEYWORD_PATH = os.getenv("PORCUPINE_KEYWORD_PATH", "").strip()
KEYWORD_NAME = os.getenv("PORCUPINE_KEYWORD_NAME", "porcupine").strip()

if not PORCUPINE_ACCESS_KEY:
    raise SystemExit("PORCUPINE_ACCESS_KEY is not set. Add it to .env or your environment.")

# -------------------------------------------------------
# Wake callback
# -------------------------------------------------------
def on_wake():
    print("[WAKE] Wake word detected!")
    Path("edge/wake/wake.flag").write_text(str(time.time()))

# -------------------------------------------------------
# Initialize Porcupine
# -------------------------------------------------------
if PORCUPINE_KEYWORD_PATH:
    porcupine = pvporcupine.create(
        keyword_paths=[PORCUPINE_KEYWORD_PATH],
        access_key=PORCUPINE_ACCESS_KEY
    )
    print("[Porcupine] Using custom keyword:", PORCUPINE_KEYWORD_PATH)
else:
    porcupine = pvporcupine.create(
        keywords=[KEYWORD_NAME],
        access_key=PORCUPINE_ACCESS_KEY
    )
    print("[Porcupine] Using built-in keyword:", KEYWORD_NAME)

sr = porcupine.sample_rate          # 16000
fl = porcupine.frame_length         # Typically 512

print(f"[Porcupine] ready (sr={sr}, frame_length={fl})")

# -------------------------------------------------------
# Audio callback — CLEAN, Windows-safe
# -------------------------------------------------------
def audio_callback(indata, frames, time_info, status):
    if status:
        print("[Audio Warning]", status)

    # RawInputStream provides raw bytes → convert to int16 numpy array
    pcm = np.frombuffer(indata, dtype=np.int16)

    try:
        result = porcupine.process(pcm)
        if result >= 0:  # wake-word detected
            on_wake()
    except Exception as e:
        print("[Porcupine Error]", e)

# -------------------------------------------------------
# Stream Loop
# -------------------------------------------------------
print("Starting audio stream... say the wake-word to trigger")

with sd.RawInputStream(
    samplerate=sr,
    blocksize=fl,
    dtype='int16',
    channels=1,
    callback=audio_callback
):
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Stopped Porcupine listener.")
    finally:
        porcupine.delete()
