Running the full Phase0+Phase1 local demo

1) Copy your .env to project root or cloud/api/.env (it must contain OPENAI_API_KEY, PORCUPINE_ACCESS_KEY etc.).
   Example path (you uploaded): /mnt/data/.env. Place or copy it to the project root.

2) Open PowerShell, cd to project root and run:
   .\.venv\Scripts\Activate.ps1
   .\scripts\dev_automation.ps1

3) Start Porcupine wake listener (in a separate terminal):
   python edge/wake/wake_word.py

4) Start edge client (separate terminal):
   python edge/client_app/edge_client.py

5) Say the wake-word (or create the wake.flag manually) and test the flow.

Notes:
- whisper.cpp must be built separately to enable local ASR. Set WHISPER_CPP_BIN and WHISPER_MODEL_PATH in your .env.
- OpenAI TTS uses audio.speech endpoint; ensure OPENAI_API_KEY is set in .env.
- For production, replace echo-style mock intent routing with LangGraph orchestrator.
