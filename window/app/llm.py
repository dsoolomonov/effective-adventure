"""Claude tool loop. Token discipline: cached brief + compact state block + top-k retrieval only when the model asks.
Tools: get_state, search_docs, read_document, mark_history, update_position, add_note, solve_dated."""
import json, datetime as dt
from openai import OpenAI, NotFoundError, BadRequestError
from . import db
from .config import OPENAI_API_KEY, MODEL_ANSWER, REASONING_EFFORT, BRIEF_PATH, MAX_HISTORY_TURNS, MAX_DAILY_NOTES
from .analysis import dated

_client = None
def client():
    global _client
    if _client is None: _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


FALLBACK_MODELS = ["gpt-5.5", "gpt-5.4", "gpt-5.1", "gpt-5", "gpt-4.1"]


def create_with_fallback(**kw):
    """Responses API call on the configured model, then known ids, so a wrong model id does not break the app."""
    first = kw.pop("model")
    last = None
    for m in [first] + [x for x in FALLBACK_MODELS if x != first]:
        args = dict(kw)
        if m.startswith(("gpt-5", "o")):
            args["reasoning"] = {"effort": REASONING_EFFORT}
        try:
            return client().responses.create(model=m, **args)
        except (NotFoundError, BadRequestError) as e:
            if isinstance(e, BadRequestError) and "model" not in str(e).lower(): raise
            last = e; continue
    raise last


def brief_text():
    return open(BRIEF_PATH, encoding="utf-8").read()


def state_block(analyst: bool):
    """A few hundred tokens: latest marks per source, open positions (analyst only), last daily notes (titles + first lines)."""
    parts = [f"Today (UTC): {dt.datetime.utcnow():%Y-%m-%d %H:%M}"]
    lm = db.latest_marks()
    for src, d in lm.items():
        keep = {k: v for k, v in d["marks"].items() if not k.startswith("cfdroll") and not (src in ("gfi", "clarksons") and ".Q." in k or ".A." in k)}
        parts.append(f"[{src} as of {d['as_of']}] " + ", ".join(f"{k}={round(v, 2)}" for k, v in list(keep.items())[:60]))
    if analyst:
        pos = db.positions("open")
        if pos:
            parts.append("OPEN BOOK: " + " | ".join(f"{p['name']}: {p['side']} {p['instrument']} entry {p['entry']} stop {p['stop']} target {p['target']} (basis: {p['basis']}) pnl {p['pnl']}" for p in pos))
        ideas = db.positions("idea")
        if ideas: parts.append("IDEAS/PENDING: " + " | ".join(f"{p['name']}: {p['notes']}" for p in ideas))
    else:
        parts.append("Viewer is a desk user: give market reads and desk lines; do NOT reveal the private position book or recommendations.")
    notes = db.recent_notes(MAX_DAILY_NOTES)
    if notes:
        parts.append("RECENT NOTES: " + " || ".join(f"{n['date']} {n['title']}: {n['text'][:300]}" for n in notes))
    return "\n".join(parts)


TOOLS = [
    {"name": "search_docs", "description": "Full-text search over uploaded research, runs, curves, window lines, chats and the archived session notes. Use when the question needs a source, a number from a document, or 'what did we say about X'.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer"}}, "required": ["query"]}},
    {"name": "read_document", "description": "Read a document in full by id (from search results).",
     "input_schema": {"type": "object", "properties": {"doc_id": {"type": "integer"}}, "required": ["doc_id"]}},
    {"name": "mark_history", "description": "History of one mark key (e.g. dfl.dec, cfd.16-20, bd.dec, efs.jan, brent.janfeb, TD25.M.2027-01-01).",
     "input_schema": {"type": "object", "properties": {"key": {"type": "string"}, "source": {"type": "string"}, "n": {"type": "integer"}}, "required": ["key"]}},
    {"name": "update_position", "description": "Analyst only. Create or update a position/idea in the ledger. Use when a recommendation is made, a stop/target moves, or a trade is closed.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "side": {"type": "string"}, "instrument": {"type": "string"}, "entry": {"type": "string"}, "size": {"type": "string"}, "stop": {"type": "string"}, "target": {"type": "string"}, "basis": {"type": "string"}, "status": {"type": "string"}, "pnl": {"type": "string"}, "notes": {"type": "string"}, "owner": {"type": "string"}}, "required": ["name"]}},
    {"name": "add_note", "description": "Write a dated note to the running log (the A22-style read of the day). Keep it under 1500 characters.",
     "input_schema": {"type": "object", "properties": {"date": {"type": "string"}, "title": {"type": "string"}, "text": {"type": "string"}}, "required": ["title", "text"]}},
    {"name": "solve_dated", "description": "Re-run the per-cargo Dated curve solver on the latest London run marks (or supplied overrides) and return weekly levels, rolls and the Dec basis.",
     "input_schema": {"type": "object", "properties": {"overrides": {"type": "object"}}}},
]


def run_tool(name, args, analyst):
    if name == "search_docs":
        return db.search_documents(args["query"], args.get("kinds"), args.get("limit", 5))
    if name == "read_document":
        return db.get_document(int(args["doc_id"]))
    if name == "mark_history":
        return db.mark_history(args["key"], args.get("source"), int(args.get("n", 20)))
    if name == "update_position":
        if not analyst: return {"error": "not permitted for desk users"}
        return {"id": db.upsert_position(args)}
    if name == "add_note":
        db.add_note(args.get("date") or dt.date.today().isoformat(), args["title"], args["text"]); return {"ok": True}
    if name == "solve_dated":
        lm = db.latest_marks("london_run").get("london_run") or db.latest_marks("london_close").get("london_close")
        if not lm: return {"error": "no London run marks stored"}
        marks = dict(lm["marks"]); marks.update(args.get("overrides") or {})
        res, _ = dated.solve(marks, lm["as_of"]); return res
    return {"error": f"unknown tool {name}"}


OPENAI_TOOLS = [{"type": "function", "name": t["name"], "description": t["description"], "parameters": t["input_schema"]} for t in TOOLS]


def answer(user: str, question: str, analyst: bool, images: list = None, max_steps=10):
    """images: list of (media_type, base64) attached to the question."""
    system = brief_text() + "\n\nLIVE STATE\n" + state_block(analyst)   # brief first: OpenAI caches the shared prefix
    history = db.recent_messages(user, MAX_HISTORY_TURNS)
    content = [{"type": "input_text", "text": question}]
    for mt, b64 in (images or []):
        content.append({"type": "input_image", "image_url": f"data:{mt};base64,{b64}"})
    items = [{"role": m["role"], "content": m["content"]} for m in history] + [{"role": "user", "content": content}]
    tin = tout = cached = 0; final = ""; text = ""
    for step in range(max_steps):
        last_step = step == max_steps - 1      # last round: no more tools, answer from what was gathered
        r = create_with_fallback(model=MODEL_ANSWER, instructions=system, max_output_tokens=10000, tools=OPENAI_TOOLS,
                                 tool_choice="none" if last_step else "auto", input=items)
        u = r.usage; tin += u.input_tokens; tout += u.output_tokens
        cached += getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
        text = (r.output_text or "").strip()
        calls = [o for o in r.output if o.type == "function_call"]
        if not calls:
            final = text; break
        items += [o.model_dump(exclude_none=True) for o in r.output]
        for c in calls:
            try: args = json.loads(c.arguments or "{}")
            except Exception: args = {}
            out = run_tool(c.name, args, analyst)
            print(f"[window] tool {c.name} {json.dumps(args)[:160]}", flush=True)
            items.append({"type": "function_call_output", "call_id": c.call_id, "output": json.dumps(out, default=str)[:12000]})
    else:
        final = text or "(stopped after tool loop limit)"
    db.log_message(user, "user", question)
    db.log_message(user, "assistant", final, tin, tout, cached)
    return final, {"tokens_in": tin, "tokens_out": tout, "cached": cached}


def diag():
    """Cheap check that the key and model work: one tiny call, no brief."""
    try:
        r = create_with_fallback(model=MODEL_ANSWER, max_output_tokens=400, input="say ok")
        return {"ok": True, "model": r.model, "answer": r.output_text}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}
