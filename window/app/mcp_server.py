"""Minimal remote MCP server (JSON-RPC over HTTP POST) so claude.ai can push uploads here as a custom connector.
Mounted at /mcp/{token}. Tools: ingest_text, ingest_file, get_state, search_docs, add_note, update_position."""
import base64, json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from .config import MCP_TOKEN
from . import db, ingest as ing, llm

router = APIRouter()

MCP_TOOLS = [
    {"name": "ingest_text", "description": "Store a pasted text input (broker run, Sing curve, Platts line, research note, chat) in The Window; parses marks and rebuilds dependent models.",
     "inputSchema": {"type": "object", "properties": {"filename": {"type": "string"}, "text": {"type": "string"}, "as_of": {"type": "string"}, "hint": {"type": "string"}}, "required": ["filename", "text"]}},
    {"name": "ingest_file", "description": "Store a file (base64) in The Window: xlsx, csv, pdf, png/jpg.",
     "inputSchema": {"type": "object", "properties": {"filename": {"type": "string"}, "data_base64": {"type": "string"}, "as_of": {"type": "string"}, "hint": {"type": "string"}}, "required": ["filename", "data_base64"]}},
    {"name": "get_state", "description": "Latest marks per source, open positions and recent notes.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "search_docs", "description": "Full-text search over stored documents.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    {"name": "add_note", "description": "Append a dated note (the day's read).", "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}, "title": {"type": "string"}, "text": {"type": "string"}}, "required": ["title", "text"]}},
    {"name": "update_position", "description": "Create/update a ledger entry.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "side": {"type": "string"}, "instrument": {"type": "string"}, "entry": {"type": "string"}, "size": {"type": "string"}, "stop": {"type": "string"}, "target": {"type": "string"}, "basis": {"type": "string"}, "status": {"type": "string"}, "pnl": {"type": "string"}, "notes": {"type": "string"}, "owner": {"type": "string"}}, "required": ["name"]}},
]


def _call(name, a):
    if name == "ingest_text": return ing.ingest(a["filename"], text=a["text"], as_of=a.get("as_of"), hint=a.get("hint", ""))
    if name == "ingest_file": return ing.ingest(a["filename"], data=base64.b64decode(a["data_base64"]), as_of=a.get("as_of"), hint=a.get("hint", ""))
    if name == "get_state": return {"marks": db.latest_marks(), "positions": db.positions("open"), "notes": db.recent_notes(5)}
    if name == "search_docs": return db.search_documents(a["query"], None, int(a.get("limit", 5)))
    if name == "add_note": db.add_note(a.get("date"), a["title"], a["text"]); return {"ok": True}
    if name == "update_position": return {"id": db.upsert_position(a)}
    raise ValueError(name)


@router.post("/mcp/{token}")
async def mcp(token: str, request: Request):
    import hmac
    if not MCP_TOKEN or not hmac.compare_digest(token, MCP_TOKEN): raise HTTPException(401)
    body = await request.json()
    reqs = body if isinstance(body, list) else [body]
    out = []
    for req in reqs:
        rid = req.get("id"); method = req.get("method"); params = req.get("params") or {}
        try:
            if method == "initialize":
                res = {"protocolVersion": params.get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}},
                       "serverInfo": {"name": "the-window", "version": "0.1"}}
            elif method == "notifications/initialized" or method == "ping":
                if rid is None: continue
                res = {}
            elif method == "tools/list":
                res = {"tools": MCP_TOOLS}
            elif method == "tools/call":
                r = _call(params["name"], params.get("arguments") or {})
                res = {"content": [{"type": "text", "text": json.dumps(r, default=str)[:20000]}]}
            else:
                out.append({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method {method}"}}); continue
            out.append({"jsonrpc": "2.0", "id": rid, "result": res})
        except Exception as e:
            out.append({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(e)}})
    if not out: return JSONResponse(status_code=202, content=None)
    return JSONResponse(out[0] if not isinstance(body, list) else out)
