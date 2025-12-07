from __future__ import annotations

from typing import Any, Dict, Optional
import json
import logging

from cloud.api.assistant.memory.semantic import semantic_memory
from cloud.api.assistant.agents import _call_openai_chat, OPENAI_MODEL_CHAT

logger = logging.getLogger(__name__)


class MemoryWriteAgent:
    """
    Decides what is worth storing as semantic memory.

    Output JSON schema (STRICT):

    {
      "store": boolean,
      "kind": "preference" | "fact" | "behavior" | "identity",
      "text": string,
      "confidence": number (0-1),
      "reason": string
    }

    Rules:
      - Only store if confidence >= 0.7
      - Never store guesses
      - Never store emotional states
      - Never store short-term context
      - Preferences > facts > habits > identity
    """

    def __init__(self, model: str = OPENAI_MODEL_CHAT) -> None:
        self.model = model

    async def decide_and_store(
        self,
        *,
        message: str,
        reply: str,
        device: Dict[str, Any],
        reasoning: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze one user turn and decide whether to write semantic memory.

        Returns:
            Stored object if saved, else None
        """

        system_prompt = (
            "You are MemoryWriteAgent inside Cypher.\n"
            "Your job is to decide whether the following interaction contains a "
            "stable, long-term memory worth storing.\n\n"
            "DO NOT store:\n"
            "- temporary goals\n"
            "- emotional statements\n"
            "- instructions\n"
            "- plans\n"
            "- one-off facts\n"
            "- schedule\n\n"
            "ONLY store:\n"
            "- preferences\n"
            "- habits\n"
            "- long-term facts\n"
            "- identity traits\n\n"
            "STRICT JSON format ONLY.\n\n"
            "Schema:\n"
            "{\n"
            "  \"store\": boolean,\n"
            "  \"kind\": \"preference\" | \"fact\" | \"behavior\" | \"identity\",\n"
            "  \"text\": string,\n"
            "  \"confidence\": number,\n"
            "  \"reason\": string\n"
            "}\n"
        )

        user_prompt = json.dumps(
            {
                "user_message": message,
                "assistant_reply": reply,
                "reasoning": reasoning,
            },
            ensure_ascii=False,
            indent=2,
        )

        raw = await _call_openai_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=self.model,
        )

        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("MemoryWriteAgent JSON invalid, raw=%r", raw)
            return None

        # Validate
        if not data.get("store"):
            return None

        try:
            confidence = float(data.get("confidence", 0.0))
        except Exception:
            confidence = 0.0

        if confidence < 0.7:
            return None

        kind = data.get("kind")
        text = str(data.get("text") or "").strip()
        reason = str(data.get("reason") or "").strip()

        if not text or kind not in ("preference", "fact", "behavior", "identity"):
            return None

        # Actually store semantic memory
        try:
            semantic_memory.add_item(
                device=device,
                kind=kind,
                text=text,
                metadata={
                    "reason": reason,
                    "confidence": confidence,
                    "source": "conversation",
                },
            )
        except Exception:
            logger.exception("Failed to store semantic memory")

        logger.info("Stored semantic memory: [%s] %s", kind, text)

        return {
            "kind": kind,
            "text": text,
            "confidence": confidence,
            "reason": reason,
        }
