import asyncio
import sys

try:
    from mcp.server.stdio import stdio_server
    from mcp.server import Server
    from mcp.types import Tool, TextContent, EmbeddedResource
    import mcp.types as types
except ImportError:
    print("MCP SDK not installed", file=sys.stderr)
    sys.exit(1)

app = Server("demo-server")

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="echo_upper",
            description="Echoes input in uppercase",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                },
                "required": ["text"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "echo_upper":
        text = str(arguments.get("text", ""))
        return [types.TextContent(type="text", text=text.upper())]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
