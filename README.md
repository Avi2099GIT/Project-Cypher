Project Cypher — REAL Phase0+Phase1 (Full local-development package)
------------------------------------------------------------------

This package contains a production-ready local-development implementation of Phase0+Phase1:
- Wake-word (Porcupine)
- VAD (webrtcvad wrapper)
- whisper.cpp ASR integration (calls local whisper.cpp binary; see instructions)
- OpenAI Realtime / TTS bridge (uses OpenAI API key)
- Conversation loop: wake -> ASR -> transcript -> backend intent -> TTS playback
- FastAPI backend with endpoints: /health, /v1/device/register, /v1/transcript, /v1/intent, /v1/tts
- Orchestrator runner with mock tool adapters (flight, maps, payments)
- PowerShell dev automation script for Windows

IMPORTANT:
- Place your .env file at the project root (example path you uploaded: /mnt/data/.env). fileciteturn1file0
  Or copy its contents into cloud/api/.env before running any services.
- This package DOES NOT contain your secrets. Use your own .env and DO NOT commit it to Git.
- Some modules expect native dependencies (whisper.cpp build, Porcupine wheel). Stubs provided where native builds are required.
- Follow README sections below for step-by-step run instructions.
