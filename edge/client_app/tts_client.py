import os
import requests
import subprocess
import wave
import simpleaudio as sa
from pathlib import Path
from dotenv import load_dotenv

ROOT_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(ROOT_ENV, override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[TTS] WARNING: OPENAI_API_KEY not set!")


# ----------------------------
# FETCH TTS → MP3 (OpenAI)
# ----------------------------
def fetch_tts_and_save(text: str, out_path: str, voice: str = "shimmer") -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")

    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini-tts",
        "input": text,
        "audio": {
            "voice": voice,
            "format": "wav"     # OpenAI STILL returns MP3, but we'll decode it
        }
    }

    print(f"[TTS] Requesting voice '{voice}'…")

    response = requests.post(url, json=payload, headers=headers, timeout=60)

    if response.status_code != 200:
        raise RuntimeError(f"TTS failed: {response.status_code} {response.text}")

    # Save MP3 data first
    mp3_path = Path(out_path).with_suffix(".mp3")
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    mp3_path.write_bytes(response.content)

    print(f"[TTS] Saved MP3 → {mp3_path}")

    # Then convert → WAV
    wav_path = Path(out_path)
    convert_mp3_to_wav(mp3_path, wav_path)

    print(f"[TTS] Converted WAV → {wav_path}")
    return str(wav_path)


# ----------------------------
# MP3 → WAV using ffmpeg
# ----------------------------
def convert_mp3_to_wav(mp3_path: Path, wav_path: Path):
    cmd = [
        "ffmpeg", "-y",
        "-i", str(mp3_path),
        "-ac", "1",
        "-ar", "16000",
        str(wav_path)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion failed:\n{result.stderr.decode()}")


# ----------------------------
# WAV PLAYBACK
# ----------------------------
def play_wav_sync(wav_path: str):
    wav_path = Path(wav_path)

    with wave.open(str(wav_path), 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        channels = wf.getnchannels()
        rate = wf.getframerate()
        sample_width = wf.getsampwidth()

    play_obj = sa.play_buffer(
        frames,
        num_channels=channels,
        bytes_per_sample=sample_width,
        sample_rate=rate
    )

    play_obj.wait_done()
