from cloud.api.assistant.mcp_clients.shell_mcp import ShellMCP
import asyncio

async def main():
    shell = ShellMCP()
    print(f"Shell Enabled: {shell.enabled}")
    
    # Test valid command
    print("\nExecuting 'echo hello world'...")
    try:
        res = await shell.call(tool="exec", payload={"cmd": "echo hello world"})
        print(f"Success: {res.success}")
        print(f"Payload: {res.payload}")
        print(f"Error: {res.error}")
    except Exception as e:
        print(f"CRASH: {e}")

if __name__ == "__main__":
    asyncio.run(main())
