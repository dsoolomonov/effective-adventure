"""Ingestion: file or text in -> document stored, marks extracted, derived rebuilds triggered, daily note stub written.
Token-cheap by design: regex parsers for the recurring formats; the parse model is only used for images and
for a 6-line summary of long research so search has something short to match on."""
import os, re, json, base64, datetime as dt
from . import db
from .config import DATA_DIR, MODEL_PARSE, OPENAI_API_KEY
from .parsers import classify, parse
from .analysis import dated

FILES = os.path.join(DATA_DIR, "files")
os.makedirs(FILES, exist_ok=True)


def _save(filename, data: bytes):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:120]
    path = os.path.join(FILES, dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S_") + safe)
    with open(path, "wb") as f: f.write(data)
    return path


def _pdf_text(path):
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    except Exception as e:
        return f"[pdf text extraction failed: {e}]"


def _xlsx_text(path, max_cells=4000):
    import openpyxl
    out = []
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        n = 0
        for ws in wb.worksheets:
            out.append(f"## sheet {ws.title}")
            for row in ws.iter_rows(values_only=True):
                vals = [str(v) for v in row if v is not None]
                if vals: out.append(" | ".join(vals)); n += len(vals)
                if n > max_cells: out.append("..."); break
    except Exception as e:
        out.append(f"[xlsx read failed: {e}]")
    return "\n".join(out)


def _office_text(path, max_chars=60000):
    """docx/pptx: strip XML from the zip (no extra dependency)."""
    import zipfile
    out = []
    try:
        z = zipfile.ZipFile(path)
        names = [n for n in z.namelist() if n.endswith(".xml") and ("word/document" in n or "ppt/slides/slide" in n or "ppt/notesSlides" in n)]
        for n in sorted(names):
            xml = z.read(n).decode("utf-8", errors="ignore")
            txt = re.sub(r"<[^>]+>", " ", xml); txt = re.sub(r"\s+", " ", txt)
            out.append(txt.strip())
    except Exception as e:
        out.append(f"[office text extraction failed: {e}]")
    return "\n".join(out)[:max_chars]


def _parse_call(prompt_content, max_tokens):
    from .llm import client
    for m in [MODEL_PARSE, "gpt-5.4-mini", "gpt-5-mini", "gpt-4.1-mini"]:
        try:
            kw = {"reasoning_effort": "low"} if m.startswith("gpt-5") else {}
            r = client().chat.completions.create(model=m, max_completion_tokens=max_tokens + 2000, messages=[{"role": "user", "content": prompt_content}], **kw)
            return r.choices[0].message.content or ""
        except Exception as e:
            if "model" in str(e).lower(): continue
            raise
    raise RuntimeError("no parse model available")


def _describe_image(path, hint=""):
    """One call on the parse model: turn a screenshot into text (numbers verbatim)."""
    if not OPENAI_API_KEY: return "[image stored; no API key to describe it]"
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    mt = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    prompt = ("Transcribe every number, label, level and lot size visible, in reading order, as compact text. "
              "If it is a Bridgeton systematic screen, list strategy, order, contract, level, lots and the position %. "
              "If it is a Platts window or a chat, transcribe the lines verbatim. No commentary. " + hint)
    return _parse_call([{"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}}, {"type": "text", "text": prompt}], 900)


def _summarise(text):
    if not OPENAI_API_KEY or len(text) < 2500: return None
    return _parse_call("Summarise this oil-market note in 6 lines for a trading desk: source, date, the numbers that matter, the view. Text:\n\n" + text[:14000], 400)


def guess_source(filename, text):
    tl = (text or "")[:3000].lower(); f = (filename or "").lower()
    for k, v in (("rystad", "Rystad"), ("energy aspects", "Energy Aspects"), ("fge nexanteca", "FGE"), ("bloomberg", "Bloomberg"),
                 ("kpler", "Kpler"), ("platts", "Platts"), ("jlc", "JLC"), ("gfi", "GFI"), ("clarksons", "Clarksons"),
                 ("leonidas", "Leonidas"), ("claytonidas", "Claytonidas"), ("aem morning", "AEM"), ("morning run", "broker"), ("indicative curve", "broker")):
        if k in tl or k in f: return v
    return None


def ingest(filename: str, data: bytes = None, text: str = None, as_of: str = None, hint: str = "", rebuild=True):
    """Returns a dict describing what was stored and what was rebuilt."""
    path = _save(filename, data) if data is not None else None
    f = (filename or "").lower()
    if text is None:
        if f.endswith(".pdf"): text = _pdf_text(path)
        elif f.endswith((".xlsx", ".xls")): text = _xlsx_text(path)
        elif f.endswith((".docx", ".pptx")): text = _office_text(path)
        elif f.endswith((".png", ".jpg", ".jpeg")): text = _describe_image(path, hint)
        else:
            try: text = data.decode("utf-8", errors="replace")
            except Exception: text = ""
    kind = classify(filename, text)
    as_of = as_of or _date_from_text(text) or dt.date.today().isoformat()
    source = guess_source(filename, text)
    try:
        parsed = parse(kind, filename, text, path, as_of)
    except Exception as e:
        parsed = None; hint = (hint + f" [parse failed: {e}]")
    meta = {"hint": hint}
    summary = None
    if kind in ("research", "other", "barometers", "document") and len(text) > 2500:
        summary = _summarise(text); meta["summary"] = summary
    doc_id = db.add_document(filename, kind, (summary + "\n\n" if summary else "") + text, as_of=as_of, source=source, meta=meta, path=path)
    result = {"doc_id": doc_id, "kind": kind, "as_of": as_of, "source": source, "chars": len(text)}
    if parsed:
        pkind, pas_of, marks, units, pmeta = parsed
        src = {"morning_run": "london_run", "closing_run": "london_close", "sing_curve": "sing_curve", "freight_csv": pmeta.get("source", "freight"), "cot_xlsx": "cot"}.get(pkind, pkind)
        db.add_marks(pas_of, src, marks, units, doc_id)
        result.update(marks=len(marks), source_key=src, as_of=pas_of, identities={k: v for k, v in marks.items() if k.startswith("derived.")})
        if pkind in ("morning_run", "closing_run") and rebuild:
            res, daily = dated.solve(marks, pas_of)
            note = f"{pas_of} {pkind}: " + ", ".join(f"{k}={v}" for k, v in marks.items() if k.startswith(("cfd.", "dfl.", "brent.")))
            xlsx = dated.write_workbook(marks, pas_of + ("_am" if pkind == "morning_run" else "_close"), res, daily, note)
            result.update(curve=res, workbook=os.path.basename(xlsx))
            db.add_note(pas_of, f"{pkind} ingested", "Marks: " + json.dumps({k: v for k, v in marks.items() if not k.startswith("cfdroll")}) +
                        f"\nWeekly levels vs Jan: {json.dumps(res['weeks'])}\nRolls: {json.dumps(res['rolls'])}")
        elif pkind == "sing_curve":
            db.add_note(pas_of, "sing curve ingested", json.dumps(marks))
    return result


def _date_from_text(text):
    t = text or ""
    m = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})", t[:3000], re.I)
    if m:
        try: return dt.datetime.strptime(f"{m.group(1)} {m.group(2)[:3]} {m.group(3)}", "%d %b %Y").date().isoformat()
        except Exception: pass
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", t[:3000])
    if m: return m.group(0)
    m = re.search(r"\[(\d{1,2}):\d{2} [AP]M, (\d{1,2})/(\d{1,2})/(20\d{2})\]", t[:500])
    if m: return f"{m.group(4)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def seed_library(folder, log=print):
    """Ingest every file under seed/library (outputs + uploads) once, in the background; skips names already stored."""
    from sqlalchemy import select
    with db.Session() as s:
        have = set(r[0] for r in s.execute(select(db.Document.filename)).all())
    n = 0
    for root, _, files in os.walk(folder):
        for fn in sorted(files):
            if fn in have or fn.startswith("."): continue
            p = os.path.join(root, fn)
            try:
                with open(p, "rb") as fh: data = fh.read()
                as_of = None
                m = re.search(r"(20\d{2})(\d{2})(\d{2})", fn) or re.search(r"(\d{1,2})(Oct|Nov|Dec)(20\d{2})", fn)
                if m and len(m.groups()) == 3 and m.group(2).isdigit(): as_of = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                r = ingest(fn, data=data, as_of=as_of, hint="seed library " + os.path.basename(root), rebuild=False)
                n += 1
                if n % 25 == 0: log(f"seed library: {n} files")
            except Exception as e:
                log(f"seed library: {fn} failed: {e}")
    return n


def seed_corpus(folder):
    """Load the exported session notes (seed/corpus/*.md) once."""
    n = 0
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".md"): continue
        p = os.path.join(folder, fn); text = open(p, encoding="utf-8").read()
        # split by analyst/input blocks so search hits are focused
        blocks = [b.strip() for b in text.split("\n---\n") if len(b.strip()) > 200]
        for i, b in enumerate(blocks):
            db.add_document(f"{fn}#{i}", "session_note", b, as_of=fn[:10], source="desk session", meta={"seed": True})
            n += 1
    return n
