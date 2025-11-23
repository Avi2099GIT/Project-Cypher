# cloud/api/intent_handler.py
"""
Intent handler for Cypher — Phase 1B
Adds natural-language reply_text for voice responses.
"""

def handle_intent(intent: str, params: dict):
    intent = intent.lower()
    params = params or {}

    # -------------------------------
    # SEARCH FLIGHTS INTENT
    # -------------------------------
    if intent == "search_flights":
        origin = params.get("origin", "BLR").upper()
        destination = params.get("destination", "DEL").upper()

        result = {
            "provider": "Amadeus-mock",
            "origin": origin,
            "destination": destination,
            "options": [
                {
                    "airline": "IndiGo",
                    "flight_no": "6E111",
                    "depart": "2025-12-24T09:00:00+05:30",
                    "price": {"amount": 3500, "currency": "INR"}
                }
            ]
        }

        reply = f"I found flights from {origin} to {destination}. The best option is IndiGo flight 6E111 at nine AM for ₹3500. Should I book it?"

        return {"result": result, "reply_text": reply}


    # -------------------------------
    # ETA INTENT
    # -------------------------------
    if intent == "get_eta":
        result = {"eta_minutes": 28}

        reply = "Your estimated time of arrival is twenty eight minutes."

        return {"result": result, "reply_text": reply}


    # -------------------------------
    # PAYMENT INTENT
    # -------------------------------
    if intent == "make_payment":
        amount = params.get("amount", 0)

        result = {"status": "pending", "amount": amount}

        reply = f"Okay. I can pay {amount} rupees. Should I proceed?"

        return {"result": result, "reply_text": reply}


    # -------------------------------
    # DEFAULT INTENT
    # -------------------------------
    result = {"echo": params}
    reply = "Alright. I heard you."

    return {"result": result, "reply_text": reply}
