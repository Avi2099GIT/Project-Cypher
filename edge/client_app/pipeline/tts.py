import subprocess
import os
import uuid
from edge.tts.openai_tts import synthesize_to_file
from edge.client_app.audio.speaker import play_audio


def speak(text):
    out_id = str(uuid.uuid4())

    mp3 = f"tts_{out_id}.mp3"
    wav = f"tts_{out_id}.wav"

    # Generate speech from OpenAI
    synthesize_to_file(text, mp3)

    # Convert to WAV using ffmpeg
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, wav],
        check=True
    )

    # Play WAV file
    play_audio(wav)

    # Cleanup temp files
    try:
        os.remove(mp3)
        os.remove(wav)
    except:
        pass
