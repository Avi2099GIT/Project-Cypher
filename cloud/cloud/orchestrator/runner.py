from typing import Any, Dict

class LangGraphRunner:
    def __init__(self):
        self.tools = {
            'search_flights': self.flight_search_tool,
            'get_eta': self.maps_tool,
            'make_payment': self.payment_tool,
        }

    def run_intent(self, intent: str, params: Dict[str, Any]):
        if intent in self.tools:
            return self.tools[intent](params)
        return {'error':'unknown_intent','available': list(self.tools.keys())}

    def flight_search_tool(self, params: Dict[str, Any]):
        return {'provider':'Amadeus-mock','origin':params.get('origin','BLR'),'destination':params.get('destination','DEL'),'options':[{'airline':'IndiGo','flight_no':'6E111','price':3500}]}

    def maps_tool(self, params: Dict[str, Any]):
        return {'eta_minutes': 12}

    def payment_tool(self, params: Dict[str, Any]):
        return {'status':'success','txn_id':'mock_txn_001'}
