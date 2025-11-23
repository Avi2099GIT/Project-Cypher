import os, requests, uuid
from dotenv import load_dotenv
load_dotenv()
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_KEY:
    raise SystemExit('OPENAI_API_KEY not set in env')

def synthesize_to_file(text, out_path):
    # This is a simple text->speech call using OpenAI's audio.speech endpoint (may require realtime API)
    # Implementation uses the REST audio.speech.create endpoint; adapt if OpenAI SDK has different method.
    url = 'https://api.openai.com/v1/audio/speech'
    headers = {'Authorization': f'Bearer {OPENAI_KEY}', 'Content-Type': 'application/json'}
    payload = {
    "model": "gpt-4o-mini-tts",
    "input": "Hello world",
    "audio": {
        "voice": "marin",
        "format": "wav"
    }
    }

    r = requests.post(url, json=payload, headers=headers, stream=True)
    if r.status_code != 200:
        raise RuntimeError('TTS failed: '+r.text)
    # Save audio to out_path
    with open(out_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=4096):
            if chunk:
                f.write(chunk)
    return out_path
