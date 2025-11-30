import sounddevice as sd
import numpy as np

def listen_until_silence(timeout=5):
    sr = 16000
    print(f"🎙 Recording for {timeout}s")
    frames = sd.rec(int(timeout*sr), samplerate=sr, channels=1, dtype='int16')
    sd.wait()
    pcm = frames[:, 0].astype('int16')
    return pcm.tobytes()
