import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def check_env():
    print("-------- DEBUG ENV --------")
    # 1. Check before loading
    print(f"Before load: ANTHROPIC_ADMIN_API_KEY = {'Found' if os.environ.get('ANTHROPIC_ADMIN_API_KEY') else 'Missing'}")
    
    # 2. Load with my patch logic
    env_path = Path(__file__).parent.parent / '.env'
    print(f"Loading form: {env_path.resolve()}")
    try:
        load_dotenv(dotenv_path=env_path)
    except Exception as e:
        print(f"Load failed: {e}")
        
    # 3. Check after loading
    key = os.environ.get('ANTHROPIC_ADMIN_API_KEY')
    print(f"After load: ANTHROPIC_ADMIN_API_KEY = {'Found' if key else 'Missing'}")
    
    # 4. Check ClaudeMCP Logic
    api_key_candidate = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_ADMIN_API_KEY")
    print(f"ClaudeMCP would see: {'Valid Key' if api_key_candidate else 'No Key'}")

if __name__ == "__main__":
    check_env()
