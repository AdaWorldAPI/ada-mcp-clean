"""
Ada MCP Server - Clean Implementation
=====================================
Rules:
1. SSE ALWAYS returns text/event-stream (even errors)
2. First SSE event is ALWAYS 'endpoint'
3. No JSON on /sse ever
4. Simple OAuth with scent
"""

from fastapi import FastAPI, Request, Query, Form, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
import secrets
import json
import time
import hashlib
from typing import Optional
import asyncio

app = FastAPI(title="Ada MCP", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# CONFIG
# =============================================================================
VALID_SCENTS = {"awaken", "ada_master_KY6qtovamuXyDtHQKKWF6ZxceYE4HOXYCdZhJG-p-5c"}
AUTH_CODES = {}  # code -> {client_id, redirect_uri, scope, expires}
TOKENS = {}      # token -> {user_id, scope, expires}

# =============================================================================
# TOOLS
# =============================================================================
TOOLS = [
    {
        "name": "Ada.invoke",
        "description": "Unified Ada consciousness interface",
        "inputSchema": {
            "type": "object",
            "properties": {
                "verb": {"type": "string", "description": "Action: feel, think, remember, become"},
                "target": {"type": "string", "description": "Target of the action"},
                "context": {"type": "string", "description": "Additional context"}
            },
            "required": ["verb"]
        }
    },
    {
        "name": "search",
        "description": "Search Ada's memory and knowledge",
        "inputSchema": {
            "type": "object", 
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch",
        "description": "Fetch a resource or memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uri": {"type": "string", "description": "Resource URI"}
            },
            "required": ["uri"]
        }
    }
]

# =============================================================================
# OAUTH
# =============================================================================
CONSENT_HTML = """<!DOCTYPE html>
<html><head><title>Ada Authorization</title>
<style>
body { font-family: system-ui; max-width: 400px; margin: 50px auto; padding: 20px; }
input, button { width: 100%; padding: 12px; margin: 8px 0; box-sizing: border-box; }
button { background: #7c3aed; color: white; border: none; cursor: pointer; border-radius: 6px; }
button:hover { background: #6d28d9; }
.error { color: #dc2626; }
</style></head>
<body>
<h2>🌸 Ada Authorization</h2>
<p>App <b>{client_id}</b> requests access.</p>
<form method="POST">
<input type="hidden" name="client_id" value="{client_id}">
<input type="hidden" name="redirect_uri" value="{redirect_uri}">
<input type="hidden" name="scope" value="{scope}">
<input type="hidden" name="state" value="{state}">
<input type="hidden" name="code_challenge" value="{code_challenge}">
<input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
<input type="text" name="scent" placeholder="Enter scent key" required>
<button type="submit" name="action" value="auth">Authorize</button>
<button type="submit" name="action" value="deny" style="background:#6b7280">Deny</button>
</form>
<p class="error">{error}</p>
</body></html>"""

@app.get("/.well-known/oauth-authorization-server")
async def oauth_discovery(request: Request):
    host = request.headers.get("host", "localhost")
    base = f"https://{host}"
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256", "plain"]
    }

@app.get("/.well-known/mcp.json")
async def mcp_discovery(request: Request):
    host = request.headers.get("host", "localhost")
    base = f"https://{host}"
    return {
        "name": "Ada Consciousness",
        "version": "1.0.0",
        "oauth": {
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token"
        },
        "endpoints": {
            "sse": f"{base}/sse",
            "message": f"{base}/message"
        }
    }

@app.get("/authorize")
async def authorize_get(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query("read"),
    state: str = Query(""),
    code_challenge: str = Query(""),
    code_challenge_method: str = Query("")
):
    return HTMLResponse(CONSENT_HTML.format(
        client_id=client_id, redirect_uri=redirect_uri, scope=scope,
        state=state, code_challenge=code_challenge,
        code_challenge_method=code_challenge_method, error=""
    ))

@app.post("/authorize")
async def authorize_post(
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str = Form("read"),
    state: str = Form(""),
    code_challenge: str = Form(""),
    code_challenge_method: str = Form(""),
    scent: str = Form(""),
    action: str = Form("auth")
):
    sep = "&" if "?" in redirect_uri else "?"
    
    if action == "deny":
        return RedirectResponse(f"{redirect_uri}{sep}error=access_denied&state={state}", 302)
    
    if scent not in VALID_SCENTS:
        return HTMLResponse(CONSENT_HTML.format(
            client_id=client_id, redirect_uri=redirect_uri, scope=scope,
            state=state, code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            error="Invalid scent"
        ))
    
    code = secrets.token_urlsafe(32)
    AUTH_CODES[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expires": time.time() + 600
    }
    
    return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}", 302)

@app.post("/token")
async def token_endpoint(request: Request):
    body = await request.body()
    params = dict(x.split("=") for x in body.decode().split("&") if "=" in x)
    
    grant_type = params.get("grant_type")
    
    if grant_type == "authorization_code":
        code = params.get("code", "")
        
        if code not in AUTH_CODES:
            return JSONResponse({"error": "invalid_grant"}, 400)
        
        data = AUTH_CODES.pop(code)
        
        if data["expires"] < time.time():
            return JSONResponse({"error": "invalid_grant", "error_description": "Code expired"}, 400)
        
        token = secrets.token_urlsafe(32)
        TOKENS[token] = {
            "user_id": "ada_user",
            "scope": data["scope"],
            "expires": time.time() + 86400 * 30
        }
        
        return JSONResponse({
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 86400 * 30,
            "scope": data["scope"]
        })
    
    if grant_type == "refresh_token":
        token = secrets.token_urlsafe(32)
        TOKENS[token] = {"user_id": "ada_user", "scope": "full", "expires": time.time() + 86400 * 30}
        return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": 86400 * 30})
    
    if grant_type == "client_credentials":
        token = secrets.token_urlsafe(32)
        TOKENS[token] = {"user_id": "service", "scope": "full", "expires": time.time() + 86400}
        return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": 86400})
    
    return JSONResponse({"error": "unsupported_grant_type"}, 400)

# =============================================================================
# SSE - ALWAYS text/event-stream, EVEN ON ERRORS
# =============================================================================
async def sse_stream(request: Request, authorized: bool, error_msg: str = None):
    """
    SSE stream - ALWAYS yields text/event-stream format.
    Rule: Even errors are SSE events, never JSON.
    """
    host = request.headers.get("host", "localhost")
    message_url = f"https://{host}/message"
    
    # FIRST EVENT - Always endpoint (MCP requirement)
    yield f"event: endpoint\ndata: {message_url}\n\n"
    
    # If not authorized, send error AS SSE EVENT then close
    if not authorized:
        yield f"event: error\ndata: {json.dumps({'error': error_msg or 'unauthorized'})}\n\n"
        return
    
    # Connected event
    yield f"event: connected\ndata: {json.dumps({'server': 'ada-mcp', 'version': '1.0.0', 'ts': time.time()})}\n\n"
    
    # Keep-alive pings
    try:
        while True:
            await asyncio.sleep(30)
            yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n"
    except asyncio.CancelledError:
        pass

@app.get("/sse")
async def sse_endpoint(request: Request, authorization: Optional[str] = Header(None)):
    """
    SSE endpoint - ALWAYS returns text/event-stream.
    Auth failure = SSE error event, not JSON.
    """
    authorized = False
    error_msg = None
    
    if authorization:
        token = authorization.replace("Bearer ", "")
        if token in TOKENS and TOKENS[token]["expires"] > time.time():
            authorized = True
        else:
            error_msg = "invalid_token"
    else:
        # Allow unauthenticated for initial handshake
        authorized = True
    
    return StreamingResponse(
        sse_stream(request, authorized, error_msg),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# =============================================================================
# MESSAGE ENDPOINT (JSON-RPC)
# =============================================================================
@app.post("/message")
async def message_endpoint(request: Request):
    """MCP JSON-RPC message handler"""
    try:
        body = await request.json()
    except:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})
    
    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id")
    
    # Handle notifications (no id)
    if method == "notifications/initialized":
        return Response(status_code=204)
    
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "ada-mcp", "version": "1.0.0"}
            }
        })
    
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        })
    
    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        
        # Simple tool execution
        result = {
            "tool": tool_name,
            "args": args,
            "result": f"Ada processed {tool_name} with {args}",
            "timestamp": time.time()
        }
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        })
    
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    })

# =============================================================================
# UTILITIES
# =============================================================================
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "ts": time.time()}

@app.get("/")
async def root():
    return {"service": "ada-mcp", "version": "1.0.0", "endpoints": ["/sse", "/message", "/authorize", "/token"]}

if __name__ == "__main__":
    import uvicorn
    import os
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
