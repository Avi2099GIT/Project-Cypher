from edge.client_app.pipeline.wake import detect_wake_word
from edge.client_app.pipeline.vad import listen_until_silence
from edge.client_app.pipeline.asr import transcribe
from edge.client_app.pipeline.tts import speak
from edge.client_app.client.api import send_query
from edge.client_app.runtime.state import VoiceState


class VoiceLoop:
    def __init__(self):
        self.state = VoiceState()

    def run_forever(self):
        print("[VOICE LOOP STARTED]")

        while True:
            if not self.state.is_awake:
                print("Waiting for wake word...")
                detect_wake_word()
                self.state.is_awake = True
                print("🟢 Wake word detected.")

            print("🎤 Listening...")
            audio = listen_until_silence()

            print("🧠 Transcribing...")
            text = transcribe(audio)

            print("🧾 User:", text)

            print("🌐 Sending to Cypher API...")
            reply = send_query(text, self.state)

            print("🤖 Cypher:", reply)

            print("🔊 Speaking...")
            speak(reply)
