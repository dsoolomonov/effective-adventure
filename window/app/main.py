"""The Window — desk analyst app. FastAPI + server-rendered chat UI + upload + MCP bridge."""
import os, json, base64, datetime as dt
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from . import db, ingest as ing, llm
from .config import APP_PASSWORD, ANALYST_USERS, SECRET_KEY, DATA_DIR, FRAME_ANCESTORS, EMBEDDED
from .mcp_server import router as mcp_router

app = FastAPI(title="The Window")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 30, same_site="none", https_only=True)


@app.middleware("http")
async def _frame_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {FRAME_ANCESTORS}"
    return resp
app.include_router(mcp_router)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


@app.on_event("startup")
def _startup():
    db.init_db()
    seed = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed")
    flag = os.path.join(DATA_DIR, ".seeded")
    curve = os.path.join(seed, "dated_curve.json")
    if os.path.exists(curve) and not os.path.exists(os.path.join(DATA_DIR, "dated_curve.json")):
        import shutil; shutil.copy(curve, os.path.join(DATA_DIR, "dated_curve.json"))
    if os.path.isdir(os.path.join(seed, "corpus")) and not os.path.exists(flag):
        n = ing.seed_corpus(os.path.join(seed, "corpus"))
        pos = os.path.join(seed, "positions.json")
        if os.path.exists(pos):
            for p in json.load(open(pos)): db.upsert_position(p)
        open(flag, "w").write(f"seeded {n} blocks {dt.datetime.utcnow()}")
    lib = os.path.join(seed, "library"); libflag = os.path.join(DATA_DIR, ".seeded_library")
    if os.path.isdir(lib) and not os.path.exists(libflag):
        import threading
        def _bg():
            n = ing.seed_library(lib)
            open(libflag, "w").write(f"library {n} files {dt.datetime.utcnow()}")
        threading.Thread(target=_bg, daemon=True).start()


def _user(request: Request):
    # Embedded: the host platform's password gate has already authenticated the request.
    return request.session.get("user") or ("analyst" if EMBEDDED else None)


def _analyst(request: Request):
    u = _user(request)
    if not u: return False
    return True if not ANALYST_USERS else u.lower() in ANALYST_USERS


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, name: str = Form(...), password: str = Form(...)):
    if not APP_PASSWORD or password != APP_PASSWORD:
        return templates.TemplateResponse(request, "login.html", {"error": "wrong password"})
    request.session["user"] = name.strip().lower()
    return RedirectResponse("./", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear(); return RedirectResponse("login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, key: str = "", name: str = "analyst"):
    if key and APP_PASSWORD and key == APP_PASSWORD:                      # embed as a tab: /?key=APP_PASSWORD
        request.session["user"] = name.strip().lower() or "analyst"
    if not _user(request): return RedirectResponse("login", status_code=303)
    return templates.TemplateResponse(request, "index.html", {"user": _user(request), "analyst": _analyst(request),
                                                     "marks": db.latest_marks(), "positions": db.positions("open") if _analyst(request) else [],
                                                     "notes": db.recent_notes(6), "tokens": db.token_totals(),
                                                     "history": db.recent_messages(_user(request), 6)})


@app.post("/chat")
async def chat(request: Request, q: str = Form(...), files: list[UploadFile] = File(default=[])):
    if not _user(request): raise HTTPException(401)
    images = []
    for f in files or []:
        data = await f.read()
        if not data: continue
        fn = f.filename or "upload"
        if fn.lower().endswith((".png", ".jpg", ".jpeg")):
            mt = "image/png" if fn.lower().endswith(".png") else "image/jpeg"
            images.append((mt, base64.b64encode(data).decode()))
        ing.ingest(fn, data=data, hint=q[:200])
    text, usage = llm.answer(_user(request), q, _analyst(request), images)
    return JSONResponse({"answer": text, "usage": usage})


@app.post("/upload")
async def upload(request: Request, files: list[UploadFile] = File(...), as_of: str = Form(default=""), hint: str = Form(default="")):
    if not _user(request): raise HTTPException(401)
    out = []
    for f in files:
        data = await f.read()
        out.append(ing.ingest(f.filename, data=data, as_of=as_of or None, hint=hint))
    return JSONResponse(out)


@app.post("/paste")
async def paste(request: Request, text: str = Form(...), filename: str = Form(default="pasted.txt"), as_of: str = Form(default=""), hint: str = Form(default="")):
    if not _user(request): raise HTTPException(401)
    return JSONResponse(ing.ingest(filename, text=text, as_of=as_of or None, hint=hint))


@app.get("/state")
def state(request: Request):
    if not _user(request): raise HTTPException(401)
    return {"marks": db.latest_marks(), "positions": db.positions("open") if _analyst(request) else [], "notes": db.recent_notes(10), "tokens": db.token_totals()}


@app.get("/files/{name}")
def files(request: Request, name: str):
    if not _user(request): raise HTTPException(401)
    p = os.path.join(DATA_DIR, "files", os.path.basename(name))
    if not os.path.exists(p): raise HTTPException(404)
    return FileResponse(p)


@app.get("/diag")
def diag(request: Request):
    if not _user(request): raise HTTPException(401)
    seeded = {f: open(os.path.join(DATA_DIR, f)).read() for f in (".seeded", ".seeded_library") if os.path.exists(os.path.join(DATA_DIR, f))}
    return {"api": llm.diag(), "seeded": seeded, "docs": db.token_totals(), "sources": {k: v["as_of"] for k, v in db.latest_marks().items()}}


@app.get("/health")
def health():
    return {"ok": True, "time": dt.datetime.utcnow().isoformat()}
