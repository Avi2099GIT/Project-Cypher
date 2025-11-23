# cloud/api/intent_handler.py
from datetime import datetime

def handle_intent(device_id: str, intent: str, params: dict):
    """
    Simple Phase-1 intent handler / orchestrator stub.
    Returns a consistent dict:
      { device_id, intent, result: {...}, reply_text: "..." }
    Keep this intentionally simple — Phase-2 will replace with NLU/LLM routing.
    """
    result = {}
    reply_text = "Okay. I heard you."

    if intent == "search_flights":
        # Accept params['origin'] and ['destination'] when provided.
        origin = params.get('origin', 'BLR')
        dest   = params.get('destination', 'DEL')
        # For Phase-1 use a mock provider response
        options = [
            {"airline": "IndiGo", "flight_no": "6E111", "depart": f"{datetime.utcnow().date()}T09:00:00+05:30", "price": {"amount": 3500, "currency": "INR"}},
            {"airline": "Air India", "flight_no": "AI123", "depart": f"{datetime.utcnow().date()}T12:30:00+05:30", "price": {"amount": 4200, "currency": "INR"}}
        ]
        result = {
            "provider": "Amadeus-mock",
            "origin": origin,
            "destination": dest,
            "date": str(datetime.utcnow().date()),
            "options": options
        }
        reply_text = f"I found {len(options)} flights from {origin} to {dest}. Would you like to hear the cheapest option?"

    elif intent == "get_eta":
        # Mock ETA response
        eta_minutes = 18
        result = {"eta_minutes": eta_minutes}
        reply_text = f"I estimate {eta_minutes} minutes to your destination."

    elif intent == "make_payment":
        amt = params.get('amount', 0)
        currency = params.get('currency', 'INR')
        # Phase1: stubbed payment intent
        result = {"status": "pending", "amount": amt, "currency": currency}
        reply_text = f"Okay, I will initiate a payment of {amt} {currency}. Confirm to continue."

    elif intent == "query":
        # Generic fallback. Echo back and ask if they want more.
        q = params.get('q') if params else None
        result = {"error": "unknown_intent", "available": ["search_flights", "get_eta", "make_payment"]}
        reply_text = f"Okay. I heard: \"{q}\". I can try searching flights, provide ETA, or make payments."

    else:
        result = {"error": "unsupported_intent"}
        reply_text = "Sorry, I don't support that intent yet."

    return {"device_id": device_id, "intent": intent, "result": result, "reply_text": reply_text}
