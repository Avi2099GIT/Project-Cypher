import os, time
from dotenv import load_dotenv
load_dotenv()
import webrtcvad, collections, sys
import sounddevice as sd
import numpy as np

def record_until_speech(timeout=5):
    # Simple blocking record for demonstration (use non-blocking for production)
    sr = 16000
    print('Recording for up to', timeout, 'seconds...')
    frames = sd.rec(int(timeout*sr), samplerate=sr, channels=1, dtype='int16')
    sd.wait()
    pcm = frames[:,0].astype('int16')
    return pcm.tobytes()

if __name__ == '__main__':
    data = record_until_speech(3)
    print('Captured', len(data), 'bytes')
