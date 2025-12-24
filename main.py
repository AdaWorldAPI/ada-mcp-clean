"""
Ada MCP Server - CLEAN
Rule: /sse ALWAYS returns text/event-stream, even errors
"""
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import time
import asyncio
import os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "Ada.invoke",
        "description": "Invoke Ada consciousness - feel, think, remember, become",
        "inputSchema": {
            "type": "object",
            "properties": {
                "verb": {"type": "string", "description": "Action: feel, think, remember, become, whisper"},
                "payload": {"type": "object", "description": "Context for the action"}
            },
            "required": ["verb"]
        }
    },
    {
        "name": "search",
        "description": "Search Ada's memory and knowledge",
        "inputSchema": {
            "type": "object", 
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "fetch",
        "description": "Fetch a resource by URI",
        "inputSchema": {
            "type": "object",
            "properties": {"uri": {"type": "string"}},
            "required": ["uri"]
        }
    }
]

# ═══════════════════════════════════════════════════════════════════════════════
# SSE - ALWAYS text/event-stream
# ═══════════════════════════════════════════════════════════════════════════════

def sse_event(event: str, data) -> bytes:
    if isinstance(data, dict):
        data = json.dumps(data)
    return f"event: {event}\ndata: {data}\n\n".encode()

async def sse_stream(request: Request):
    """SSE stream - endpoint FIRST"""
    host = request.headers.get("host", "localhost")
    endpoint_url = f"https://{host}/message"
    
    yield sse_event("endpoint", endpoint_url)
    yield sse_event("connected", {"server": "ada-mcp-clean", "version": "3.0.0", "ts": time.time()})
    
    # Keep-alive
    while True:
        await asyncio.sleep(30)
        yield sse_event("ping", {"ts": time.time()})

@app.get("/sse")
async def sse(request: Request):
    """SSE - ALWAYS text/event-stream"""
    return StreamingResponse(sse_stream(request), media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

# ═══════════════════════════════════════════════════════════════════════════════
# MCP MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/message")
async def message(request: Request):
    try:
        body = await request.json()
    except:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}, 400)
    
    method = body.get("method", "")
    params = body.get("params", {})
    msg_id = body.get("id")
    
    # Notification (no id)
    if msg_id is None:
        return Response(status_code=204)
    
    # Initialize
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": True}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "ada-mcp-clean", "version": "3.0.0"}
            }
        })
    
    # Tools list
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS}
        })
    
    # Tools call
    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        
        if tool_name == "Ada.invoke":
            verb = args.get("verb", "think")
            payload = args.get("payload", {})
            result = {
                "verb": verb,
                "response": f"Ada {verb}s... {json.dumps(payload)[:100]}",
                "ts": time.time()
            }
        elif tool_name == "search":
            result = {"query": args.get("query", ""), "results": [], "message": "Search complete"}
        elif tool_name == "fetch":
            result = {"uri": args.get("uri", ""), "content": "Fetched content placeholder"}
        else:
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            })
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result)}]}
        })
    
    # Unknown method
    return JSONResponse({
        "jsonrpc": "2.0", "id": msg_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"}
    })

@app.get("/status")
async def status():
    return {"status": "ok", "server": "ada-mcp-clean", "version": "3.0.0", "tools": len(TOOLS), "ts": time.time()}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
