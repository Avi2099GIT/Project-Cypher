import os, subprocess, json, tempfile
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
WHISPER_BIN = os.getenv('WHISPER_CPP_BIN','whisper.cpp/main.exe')
MODEL_PATH = os.getenv('WHISPER_MODEL_PATH','models/ggml-base.bin')

def transcribe_file(wav_path):
    """Call whisper.cpp binary (user must build) and return transcript (stub for Windows)
    Example command (depends on whisper.cpp build):
    ./main -m models/ggml-base.en.bin -f audio.wav
    """
    if not Path(WHISPER_BIN).exists():
        raise FileNotFoundError(f'Whisper binary not found: {WHISPER_BIN} (build whisper.cpp and set WHISPER_CPP_BIN env)')
    cmd = [WHISPER_BIN, '-m', MODEL_PATH, '-f', wav_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('whisper failed: '+proc.stderr)
    # naive parsing: last line is transcript
    out = proc.stdout.strip().splitlines()
    if not out:
        return ''
    return out[-1]
