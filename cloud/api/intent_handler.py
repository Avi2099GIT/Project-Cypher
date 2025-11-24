# cloud/api/intent_handler.py
import logging
from typing import Any, Dict

# Use your existing runner (LangGraphRunner)
# Ensure this import matches where your runner.py lives.
# In your project structure runner.py was at cloud/orchestrator/runner.py
from cloud.orchestrator.runner import LangGraphRunner

logger = logging.getLogger("intent_handler")
logger.setLevel(logging.INFO)

# single runner instance (lightweight mock runner) — reuse as needed
_runner = LangGraphRunner()


def _build_reply_text_for_intent(intent: str, result: Dict[str, Any]) -> str:
    """
    Create a user-friendly reply_text from the result structure.
    Phase-1/1C: keep simple, but consistent.
    """
    if not isinstance(result, dict):
        return f"Intent {intent} executed."

    # Common patterns
    if intent == "search_flights":
        origin = result.get("origin") or result.get("from") or "unknown"
        dest = result.get("destination") or result.get("to") or "unknown"
        options = result.get("options", [])
        if options:
            first = options[0]
            airline = first.get("airline", "an airline")
            price = first.get("price")
            if price:
                return f"I found flights from {origin} to {dest}. Example: {airline} at {price}."
            else:
                return f"I found flights from {origin} to {dest}. I can show options."
        return f"I searched flights from {origin} to {dest} but found no options."

    if intent == "get_eta":
        eta = result.get("eta_minutes") or result.get("eta")
        if eta:
            return f"Estimated time is {eta} minutes."
        return "I looked up the ETA but couldn't find a value."

    if intent == "make_payment":
        status = result.get("status")
        if status == "success":
            return f"Payment succeeded. Transaction id {result.get('txn_id','-')}"
        if status == "pending":
            return "Payment is pending confirmation."
        return "Payment failed or could not be completed."

    # Generic fallbacks
    if "reply_text" in result:
        return result["reply_text"]
    if "summary" in result:
        return result["summary"]
    if "message" in result:
        return result["message"]

    return f"Intent {intent} executed."


def handle_intent(device_id: str, intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Central handler used by routes_intent.py
    - device_id: origin device
    - intent: string intent name (eg "search_flights")
    - params: dict of parameters (entities)
    Returns a JSON-serializable dict that the edge client expects, e.g.:
      {
        "device_id": "<id>",
        "intent": "search_flights",
        "result": { ... runner result ... },
        "reply_text": "I found flights ..."
      }
    """
    logger.info("handle_intent called: device=%s intent=%s params=%s", device_id, intent, params)

    try:
        # Run intent via the runner (tools)
        result = _runner.run_intent(intent, params or {})
    except Exception as e:
        logger.exception("runner.run_intent failed")
        return {
            "device_id": device_id,
            "intent": intent,
            "error": "runner_failed",
            "detail": str(e),
            "reply_text": f"Sorry, an internal error occurred while executing {intent}."
        }

    # Build a friendly reply_text for TTS / edge playback
    try:
        reply_text = _build_reply_text_for_intent(intent, result)
    except Exception:
        reply_text = None

    resp = {
        "device_id": device_id,
        "intent": intent,
        "result": result,
        "reply_text": reply_text
    }
    logger.info("handle_intent response: %s", resp)
    return resp
