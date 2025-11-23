"""
Recorder for Cypher v1
Fix for HyperX SoloCast WASAPI:
 - Record at 48 kHz (supported)
 - Downsample to 16 kHz for Whisper
 - VAD-based stop
"""

import time
import os
import numpy as np
import sounddevice as sd
import soundfile as sf
import webrtcvad
from pathlib import Path
from scipy.signal import resample_poly


DEVICE_INDEX = 20            # HyperX SoloCast (WASAPI)
INPUT_RATE = 48000           # Native rate for your microphone
TARGET_RATE = 16000          # Whisper requirement
CHUNK_MS = 30
MAX_RECORD_SECS = 12
VAD_AGGRESSIVENESS = 2
SILENCE_THRESHOLD_SECS = 1.2
GAIN = 2.5


def downsample(audio, orig_sr, target_sr):
    """High-quality polyphase downsampling."""
    gcd = np.gcd(orig_sr, target_sr)
    up = target_sr // gcd
    down = orig_sr // gcd
    return resample_poly(audio, up, down)


def record_until_silence(out_wav_path):
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    frames = []

    chunk_samples = int(INPUT_RATE * CHUNK_MS / 1000)
    required_silence_chunks = int((SILENCE_THRESHOLD_SECS * 1000) / CHUNK_MS)

    print(f"[ASR] Recording at 48 kHz on device {DEVICE_INDEX} ...")

    sd.default.device = DEVICE_INDEX
    sd.default.samplerate = INPUT_RATE
    sd.default.channels = 1

    silence_chunks = 0
    start = time.time()

    while True:
        audio = sd.rec(
            frames=chunk_samples,
            samplerate=INPUT_RATE,
            channels=1,
            dtype="float32"
        )
        sd.wait()

        pcm_float = audio[:, 0] * GAIN
        pcm_float = np.clip(pcm_float, -1.0, 1.0)

        pcm_int16 = (pcm_float * 32767).astype(np.int16)
        frames.append(pcm_int16)

        if vad.is_speech(pcm_int16.tobytes(), INPUT_RATE):
            silence_chunks = 0
        else:
            silence_chunks += 1

        if silence_chunks >= required_silence_chunks:
            print("[ASR] Silence detected. Stopping.")
            break

        if (time.time() - start) > MAX_RECORD_SECS:
            print("[ASR] Max time reached. Stopping.")
            break

    audio_full = np.concatenate(frames).astype(np.float32)

    # Normalize
    peak = np.max(np.abs(audio_full))
    if peak > 0:
        audio_full /= peak

    print("[ASR] Downsampling 48 kHz → 16 kHz...")
    audio_16k = downsample(audio_full, INPUT_RATE, TARGET_RATE)
    audio_16k = np.clip(audio_16k, -1.0, 1.0)
    audio_16k = (audio_16k * 32767).astype(np.int16)

    Path(out_wav_path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_wav_path, audio_16k, TARGET_RATE, subtype="PCM_16")

    print(f"[ASR] Written WAV -> {out_wav_path} ({len(audio_16k)} samples, 16kHz)")
    return out_wav_path
