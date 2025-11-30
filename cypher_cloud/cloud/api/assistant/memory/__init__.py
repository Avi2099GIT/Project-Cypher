from __future__ import annotations

import os
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from dotenv import load_dotenv

from ..tools_base import ToolContext  # reuse same context type

load_dotenv()

try:
    import openai  # type: ignore
except Exception:  # pragma: no cover
    openai = None  # type: ignore


class MemoryService:
    """
    Hybrid-ready memory engine for Cypher.

    Current capabilities:
    - Per-device short-term history (last N messages)
    - LLM-based summary of recent conversation
    - Simple preferences
    - Local notes
    - Local tasks (todo list)

    Later:
    - Persist to DB / vector store
    - Cloud sync for multi-device / enterprise
    """

    def __init__(self, max_short_term: int = 20) -> None:
        # device_id -> state dict
        self._store: Dict[str, Dict[str, Any]] = {}
        self.max_short_term = max_short_term

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_device_id(self, device: Dict[str, Any]) -> str:
        return device.get("device_id") or device.get("id") or "unknown-device"

    def _get_state(self, device_id: str) -> Dict[str, Any]:
        if device_id not in self._store:
            self._store[device_id] = {
                "short_term": deque(maxlen=self.max_short_term),  # type: Deque[Dict[str, Any]]
                "summary": None,
                "preferences": {},
                "long_term": [],   # placeholder for future embeddings / facts
                "notes": [],       # list[str]
                "tasks": [],       # list[Dict[str, Any]] {id, text, done}
                "next_task_id": 1,
            }
        return self._store[device_id]

    # ------------------------------------------------------------------
    # History + summary
    # ------------------------------------------------------------------

    def get_short_term_history(self, device: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Returns a list of messages suitable for passing as `history`
        to PlannerAgent / ChatAgent.

        We optionally prefix with a summary if available.
        """
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        short_term: Deque[Dict[str, Any]] = state["short_term"]
        summary: Optional[str] = state.get("summary")

        history: List[Dict[str, Any]] = list(short_term)
        if summary:
            history = [
                {
                    "role": "system",
                    "content": f"Conversation summary so far: {summary}",
                }
            ] + history

        return history

    def get_memory_view(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a lightweight snapshot of memory for API responses.
        """
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)

        return {
            "summary": state.get("summary"),
            "short_term_count": len(state["short_term"]),
            "preferences": state.get("preferences", {}),
            "long_term_count": len(state.get("long_term", [])),
            "notes_count": len(state.get("notes", [])),
            "tasks_count": len(state.get("tasks", [])),
        }

    async def record_interaction(
        self,
        device: Dict[str, Any],
        user_message: str,
        reply_text: str,
        tools_used: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Update memory with the latest user ↔ assistant turn.
        """
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        short_term: Deque[Dict[str, Any]] = state["short_term"]

        # Append user + assistant messages to short-term buffer
        short_term.append(
            {
                "role": "user",
                "content": user_message,
            }
        )
        short_term.append(
            {
                "role": "assistant",
                "content": reply_text,
            }
        )

        # Optionally store tool usage as a separate assistant "thought"
        if tools_used:
            short_term.append(
                {
                    "role": "assistant",
                    "content": f"[tools_used] {tools_used}",
                }
            )

        # Recompute summary using LLM (if available)
        await self._refresh_summary(device_id, state)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def set_preference(self, device: Dict[str, Any], key: str, value: Any) -> None:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        prefs = state.setdefault("preferences", {})
        prefs[key] = value

    def get_preferences(self, device: Dict[str, Any]) -> Dict[str, Any]:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        return dict(state.get("preferences", {}))

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def add_note(self, device: Dict[str, Any], content: str) -> None:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        notes: List[str] = state.setdefault("notes", [])
        if content:
            notes.append(content)

    def get_notes(self, device: Dict[str, Any]) -> List[str]:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        return list(state.get("notes", []))

    def clear_notes(self, device: Dict[str, Any]) -> None:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        state["notes"] = []

    # ------------------------------------------------------------------
    # Tasks / todos
    # ------------------------------------------------------------------

    def add_task(self, device: Dict[str, Any], text: str) -> Dict[str, Any]:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        tasks: List[Dict[str, Any]] = state.setdefault("tasks", [])
        next_id: int = state.get("next_task_id", 1)

        task = {"id": next_id, "text": text, "done": False}
        tasks.append(task)
        state["next_task_id"] = next_id + 1
        return task

    def list_tasks(self, device: Dict[str, Any]) -> List[Dict[str, Any]]:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        return list(state.get("tasks", []))

    def complete_task(self, device: Dict[str, Any], task_id: int) -> bool:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        tasks: List[Dict[str, Any]] = state.setdefault("tasks", [])
        for t in tasks:
            if t.get("id") == task_id:
                t["done"] = True
                return True
        return False

    def clear_tasks(self, device: Dict[str, Any]) -> None:
        device_id = self._get_device_id(device)
        state = self._get_state(device_id)
        state["tasks"] = []

    # ------------------------------------------------------------------
    # LLM summary (SLM/LLM powered)
    # ------------------------------------------------------------------

    async def _refresh_summary(self, device_id: str, state: Dict[str, Any]) -> None:
        """
        Summarize the short-term history into a compact memory summary.

        Uses OpenAI for now; later can be swapped with a local SLM.
        """
        if openai is None:
            # No LLM available; keep a naive text summary
            state["summary"] = self._naive_summary(state)
            return

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            state["summary"] = self._naive_summary(state)
            return

        client = openai.OpenAI(api_key=api_key)

        short_term: Deque[Dict[str, Any]] = state["short_term"]
        if not short_term:
            return

        # Build a compact transcript
        lines: List[str] = []
        for m in list(short_term)[-10:]:
            role = m.get("role", "user")
            content = str(m.get("content", ""))[:300]
            lines.append(f"{role}: {content}")

        transcript = "\n".join(lines)

        try:
            resp = client.chat.completions.create(
                model=os.getenv("CYPHER_MEMORY_MODEL", "gpt-4o-mini"),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Cypher's memory engine. "
                            "Summarize the conversation so far into a brief, neutral memory "
                            "that captures user preferences, tasks, and important context. "
                            "Avoid speculating or inventing facts."
                        ),
                    },
                    {
                        "role": "user",
                        "content": transcript,
                    },
                ],
                temperature=0.1,
            )
            summary = (resp.choices[0].message.content or "").strip()
            state["summary"] = summary
        except Exception:
            # On any error, fall back to naive summary
            state["summary"] = self._naive_summary(state)

    def _naive_summary(self, state: Dict[str, Any]) -> str:
        """
        Super simple non-LLM fallback summary.
        """
        short_term: Deque[Dict[str, Any]] = state["short_term"]
        if not short_term:
            return ""
        last = list(short_term)[-4:]
        parts = [m.get("content", "") for m in last]
        return " | ".join(str(p)[:100] for p in parts)


# Global singleton
memory_service = MemoryService()
