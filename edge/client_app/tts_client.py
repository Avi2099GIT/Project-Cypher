# edge/client_app/tts_client.py
import os
import requests
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load root .env
ROOT_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(ROOT_ENV, override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[TTS] WARNING: OPENAI_API_KEY not set!")

# Preferred model: gpt-4o-mini-tts (or gpt-4o-realtime-preview-tts for realtime)
TTS_MODEL = os.getenv("CY_TTS_MODEL", "gpt-4o-mini-tts")

def _is_riff(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] == b'RIFF'

def fetch_tts_and_save(text: str, out_path: str, voice: str = "shimmer") -> str:
    """
    Request TTS from OpenAI, save to WAV. If OpenAI returns MP3, convert to WAV via ffmpeg (if available).
    Returns path to WAV file.
    """

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing from .env")

    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": TTS_MODEL,
        "input": text,
        "audio": {
            "voice": voice.lower(),
            # request mp3 as a safe default — some endpoints return mp3
            "format": "mp3"
        }
    }

    print(f"[TTS] Requesting voice '{voice}' for: {text}")

    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"TTS API returned {resp.status_code}: {resp.text}")

    data = resp.content
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # If the API returned a WAV (RIFF) blob, save as WAV directly
    if _is_riff(data):
        wav_path = out_path.with_suffix(".wav")
        wav_path.write_bytes(data)
        print(f"[TTS] Saved WAV → {wav_path}")
        return str(wav_path)

    # Otherwise save as mp3 and try convert to wav
    mp3_path = out_path.with_suffix(".mp3")
    mp3_path.write_bytes(data)
    print(f"[TTS] Saved MP3 → {mp3_path}")

    # Try ffmpeg conversion
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        # No ffmpeg — return mp3 path and let caller decide what to do
        raise RuntimeError("ffmpeg not found on PATH; cannot convert mp3 to wav. Install ffmpeg or set CY_TTS_MODEL to return WAV directly.")

    wav_path = out_path.with_suffix(".wav")
    cmd = [ffmpeg, "-y", "-i", str(mp3_path), "-ar", "16000", "-ac", "1", str(wav_path)]
    subprocess.run(cmd, check=True)
    print(f"[TTS] Converted WAV → {wav_path}")
    return str(wav_path)


# Simple playback using simpleaudio (blocking)
def play_wav_sync(wav_path: str):
    import wave
    import simpleaudio as sa

    wav_path = Path(wav_path).resolve()
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV not found: {wav_path}")

    with wave.open(str(wav_path), 'rb') as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    # simpleaudio requires correct channels/width — use values from file
    play_obj = sa.play_buffer(frames, num_channels=n_channels, bytes_per_sample=sampwidth, sample_rate=framerate)
    play_obj.wait_done()
