"""
Whisper.cpp wrapper for Cypher v1
Removes timestamps and metadata from output.
"""

import os
import subprocess
from pathlib import Path
import re

WHISPER_BIN = os.getenv("WHISPER_CPP_BIN")
MODEL_PATH = os.getenv("WHISPER_MODEL_PATH")

def clean_whisper_output(text: str) -> str:
    """
    Removes timestamps like:
    [00:00:00.000 --> 00:00:04.100]
    Removes [BLANK_AUDIO], [inaudible], etc.
    """
    # Remove timestamps
    text = re.sub(r"\[.*?\]", "", text)

    # Remove common labels
    text = text.replace("BLANK_AUDIO", "")
    text = text.replace("inaudible", "")

    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def transcribe_with_whispercpp(wav_path: str) -> str:
    wav_path = str(Path(wav_path).resolve())

    if not Path(WHISPER_BIN).exists():
        raise FileNotFoundError(f"Whisper binary not found: {WHISPER_BIN}")
    if not Path(MODEL_PATH).exists():
        raise FileNotFoundError(f"Whisper model not found: {MODEL_PATH}")

    cmd = [
        WHISPER_BIN,
        "-m", MODEL_PATH,
        "-f", wav_path,
        "--language", "en",
        "--output-txt",
        "--no-timestamps"
    ]

    print("[ASR] Running whisper.cpp:")
    print("      " + " ".join(cmd))

    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        print("[ASR] whisper.cpp STDERR:")
        print(proc.stderr)
        raise RuntimeError("whisper.cpp exited with an error.")

    raw = proc.stdout.strip()
    cleaned = clean_whisper_output(raw)

    print(f"[ASR] whisper.cpp output: {cleaned}")
    return cleaned
