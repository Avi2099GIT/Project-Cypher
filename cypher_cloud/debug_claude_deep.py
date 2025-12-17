import urllib.request
import json
import os

url = "http://localhost:8000/v1/assistant/query"
payload = {"message": "Ask Claude to say OK"}
data = json.dumps(payload).encode("utf-8")

req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

print(f"Sending request to {url}...")
try:
    with urllib.request.urlopen(req) as response:
        resp_body = response.read().decode("utf-8")
        data = json.loads(resp_body)
    
    print("\n--- RESPONSE DATA ---")
    print(data.keys())
    
    with open("claude_debug_full.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    print("\nSaved full response to claude_debug_full.json")
    
    if "memory_used" in data and "recent_episodes" in data["memory_used"]:
        episodes = data["memory_used"]["recent_episodes"]
        for ep in episodes:
            if ep["role"] == "assistant" and "meta" in ep and "tools_used" in ep["meta"]:
                print("\n--- TOOLS USED ---")
                print(json.dumps(ep["meta"]["tools_used"], indent=2))
                
except Exception as e:
    print(f"Request failed: {e}")
