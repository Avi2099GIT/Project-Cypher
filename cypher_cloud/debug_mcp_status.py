import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load from parent directory (cypher_edge_runtime/.env)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from cloud.api.assistant.mcp.registry import MCPRegistry
from cloud.api.assistant.mcp_clients.claude_mcp import ClaudeMCP
from cloud.api.assistant.mcp_clients.shell_mcp import ShellMCP

async def check_status():
    print("--- MCP Registry Status ---")
    
    # 1. Shell
    shell = ShellMCP()
    print(f"Client: {shell.name}")
    print(f"  Enabled: {shell.enabled}")

    # 2. Others typically in registry
    reg = MCPRegistry()
    
    # Create dummy clients to check logic if logic relies on env vars
    # (Note: Registering them doesn't change env vars, but instantiating them does check env vars)
    
    clients = ["docker", "github", "playwright", "claude", "math"]
    for name in clients:
        try:
            if name == "claude":
                 c = ClaudeMCP()
                 print(f"Client: {name}")
                 print(f"  Enabled: {c.enabled}")
            else:
                 # Just check if we can instantiate or check registry if populated
                 c = reg.get(name)
                 enabled = c.enabled if c else False
                 print(f"Client: {name}")
                 print(f"  Enabled: {enabled}")
                 if name == "github" and c:
                     print(f"  Repo: {c.repo}")
                     print(f"  Token: {'Set' if c.token else 'None'}")
        except Exception as e:
            print(f"Client: {name} Error: {e}")

    print("\n--- Probe checks ---")
    if os.environ.get("ANTHROPIC_ADMIN_API_KEY"):
         print("Env Var ANTHROPIC_ADMIN_API_KEY found.")
    else:
         print("Env Var ANTHROPIC_ADMIN_API_KEY NOT found.")

if __name__ == "__main__":
    asyncio.run(check_status())
