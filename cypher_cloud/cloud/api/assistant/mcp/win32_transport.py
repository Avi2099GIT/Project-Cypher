import asyncio
import subprocess
import threading
import sys
from typing import Optional, Dict, List, Any
from contextlib import asynccontextmanager
from mcp.types import JSONRPCMessage, JSONRPCRequest, JSONRPCResponse, JSONRPCNotification
import json

class ThreadedStreamReader:
    """Reads lines from a Queue populated by a thread."""
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    async def read_message(self) -> Optional[JSONRPCMessage]:
        line = await self.queue.get()
        if line is None:
            return None
        try:
            # Parse standard JSON-RPC message
            data = json.loads(line)
            # Basic Mapping (SDK usually does this, but we are replacing low-level transport)
            # Actually, the SDK expects high-level objects if we replace the Session.
            # But here we are replacing 'stdio_client'.
            # 'stdio_client' yields (read_stream, write_stream).
            # The SDK's 'read_stream' is expected to be an AsyncIterator or have 'receive()'?
            # Let's check typical generic_mcp usage. 
            # It uses `async with stdio_client(server_params) as (read, write):`
            # `read` is a `MemoryObjectReceiveStream[JSONRPCMessage | Exception]` in newer SDKs
            # OR just a stream of bytes/strings?
            return data # Returning dict for now, SDK might parse it.
        except Exception:
            return None

class ThreadedStreamWriter:
    """Writes to stdin of the subprocess."""
    def __init__(self, process: subprocess.Popen):
        self.process = process

    async def send_message(self, message: JSONRPCMessage):
        # Serialize and write
        # This mirrors how typical MCP stdio transport writes
        # If message is object, serialize it.
        json_str = message.model_dump_json() if hasattr(message, 'model_dump_json') else json.dumps(message)
        
        if self.process.stdin:
            try:
                self.process.stdin.write(json_str + "\n")
                self.process.stdin.flush()
            except Exception as e:
                print(f"Error writing to process: {e}")

# The SDK's stdio_client likely yields (read_stream, write_stream) 
# where read_stream is a 'anyio.streams.memory.MemoryObjectReceiveStream' 
# that yields 'JSONRPCMessage'.
# We need to mimic that interface exactly for 'GenericMcpClient' to work unmodified?
# OR we modify GenericMcpClient to accept our custom streams.

# Let's try to mimic 'anyio' streams roughly.

class SimpleReceiveStream:
    def __init__(self, queue: asyncio.Queue):
        self._queue = queue
    
    def __aiter__(self):
        return self
        
    async def __anext__(self):
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item
    
    async def receive(self):
        """Compatibility with anyio.streams.memory.MemoryObjectReceiveStream"""
        item = await self._queue.get()
        if item is None:
             raise EOFError("Stream closed")
        return item

    async def aclose(self):
        pass

class SimpleSendStream:
    def __init__(self, process: subprocess.Popen):
        self._process = process
        
    async def send(self, message: Any):
         # Message is likely a pydantic model (JSONRPCMessage)
         json_str = message.model_dump_json() if hasattr(message, 'model_dump_json') else json.dumps(message)
         if self._process.stdin:
            try:
                self._process.stdin.write(json_str + "\n")
                self._process.stdin.flush()
            except Exception:
                pass

    async def aclose(self):
        pass

@asynccontextmanager
async def win32_stdio_client(command: str, args: List[str], env: Optional[Dict[str, str]] = None):
    """
    A Windows-safe stdio client that uses Threads instead of Asyncio Subprocess.
    Yields (read_stream, write_stream).
    """
    cmd_list = [command] + list(args)
    print(f"[Win32Transport] Starting: {cmd_list}")
    
    # Start Process
    try:
        process = subprocess.Popen(
            cmd_list,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr, # Pipe stderr to main stderr for visibility
            env=env,
            text=True,
            bufsize=1, # Line buffered
            encoding='utf-8'
        )
        print(f"[Win32Transport] Started PID: {process.pid}")
    except Exception as e:
        print(f"[Win32Transport] Popen Failed: {e}")
        raise e
    
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    
    def reader_thread():
        """Reads stdout line by line and pushes to queue."""
        print(f"[Win32Transport] Reader Thread Started for PID {process.pid}")
        try:
            if process.stdout:
                for line in process.stdout:
                    if line.strip():
                        # Parse here or later? SDK expects objects.
                        try:
                            # print(f"[Win32Transport] RAW READ: {line.strip()}")
                            data = json.loads(line)
                            # We need to convert dict to JSONRPCMessage types
                            from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCNotification, JSONRPCError
                            
                            msg = None
                            if "method" in data:
                                if "id" in data:
                                    msg = JSONRPCRequest(**data)
                                else:
                                    msg = JSONRPCNotification(**data)
                            elif "result" in data or "error" in data:
                                msg = JSONRPCResponse(**data)
                            
                            if msg:
                                loop.call_soon_threadsafe(queue.put_nowait, msg)
                        except Exception as e:
                            print(f"[Win32Transport] Parse Error: {e} | Line: {line[:50]}...")
        except Exception as e:
            print(f"[Win32Transport] Thread Error: {e}")
        finally:
            print(f"[Win32Transport] Reader Thread Ending")
            loop.call_soon_threadsafe(queue.put_nowait, None) # EOF

    t = threading.Thread(target=reader_thread, daemon=True)
    t.start()
    
    try:
        read_stream = SimpleReceiveStream(queue)
        write_stream = SimpleSendStream(process)
        yield read_stream, write_stream
        print(f"[Win32Transport] Yielded streams")
    finally:
        print(f"[Win32Transport] Closing process {process.pid}")
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except:
            process.kill()
