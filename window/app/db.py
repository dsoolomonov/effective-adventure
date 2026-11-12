"""Storage: documents (raw text + search), marks (structured numbers), positions, daily notes, chat log.
Postgres on Fly (DATABASE_URL) or SQLite locally. Search = Postgres full-text when available, ILIKE otherwise."""
import os, json, datetime as dt
from sqlalchemy import (create_engine, Column, Integer, String, Text, Float, DateTime, JSON, text, select, desc)
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import DATABASE_URL, DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()
IS_PG = DATABASE_URL.startswith("postgres")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    filename = Column(String(300))
    kind = Column(String(60), index=True)          # morning_run, sing_curve, platts_window, barometers, research, freight_csv, cot_xlsx, image, chat, note, other
    uploaded_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    as_of = Column(String(10), index=True)         # YYYY-MM-DD the content refers to
    source = Column(String(120))                   # Rystad, EA, FGE, broker, Bloomberg, ...
    text = Column(Text)
    meta = Column(JSON, default=dict)
    path = Column(String(500))                     # stored file path if any


class Mark(Base):
    __tablename__ = "marks"
    id = Column(Integer, primary_key=True)
    as_of = Column(String(16), index=True)         # YYYY-MM-DD or YYYY-MM-DD HHMM
    source = Column(String(60), index=True)        # london_run, sing_curve, bbg, gfi, clarksons, cot, board
    key = Column(String(120), index=True)          # e.g. brent.janfeb, cfd.16-20, dfl.dec, bd.dec, efs.jan, td25.M.2027-01
    value = Column(Float)
    unit = Column(String(16), default="c")         # c = cents/bbl, $ = $/bbl, ws, pmt, lots, %
    doc_id = Column(Integer)


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    side = Column(String(10))                      # long / short
    instrument = Column(String(200))
    entry = Column(String(60))
    size = Column(String(60))
    stop = Column(String(60))
    target = Column(String(60))
    basis = Column(Text)                           # why the levels
    status = Column(String(20), default="open")    # open / closed / idea
    pnl = Column(String(60))
    notes = Column(Text)
    owner = Column(String(60), default="desk")     # desk / clayton / kelvin
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    date = Column(String(10), index=True)
    title = Column(String(200))
    text = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    user = Column(String(80), index=True)
    role = Column(String(12))
    content = Column(Text)
    ts = Column(DateTime, default=dt.datetime.utcnow, index=True)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    cached = Column(Integer, default=0)


def init_db():
    Base.metadata.create_all(engine)
    if IS_PG:
        with engine.begin() as con:
            con.execute(text("CREATE INDEX IF NOT EXISTS documents_fts ON documents USING gin (to_tsvector('english', coalesce(text,'')))"))


# ---------- helpers ----------
def add_document(filename, kind, text_, as_of=None, source=None, meta=None, path=None):
    with Session() as s:
        d = Document(filename=filename, kind=kind, text=text_, as_of=as_of, source=source, meta=meta or {}, path=path)
        s.add(d); s.commit(); return d.id


def add_marks(as_of, source, marks: dict, unit_map=None, doc_id=None):
    unit_map = unit_map or {}
    with Session() as s:
        for k, v in marks.items():
            if v is None: continue
            s.add(Mark(as_of=as_of, source=source, key=k, value=float(v), unit=unit_map.get(k, "c"), doc_id=doc_id))
        s.commit()


def latest_marks(source=None, limit_sources=3):
    """Latest snapshot per source: {source: {as_of, marks{key:value}}}"""
    out = {}
    with Session() as s:
        q = select(Mark.source, Mark.as_of).distinct().order_by(desc(Mark.as_of))
        if source: q = q.where(Mark.source == source)
        seen = {}
        for src, asof in s.execute(q).all():
            if src in seen: continue
            seen[src] = asof
        for src, asof in seen.items():
            rows = s.execute(select(Mark.key, Mark.value, Mark.unit).where(Mark.source == src, Mark.as_of == asof)).all()
            out[src] = {"as_of": asof, "marks": {k: v for k, v, _ in rows}}
    return out


def mark_history(key, source=None, n=20):
    with Session() as s:
        q = select(Mark.as_of, Mark.value, Mark.source).where(Mark.key == key).order_by(desc(Mark.as_of)).limit(n)
        if source: q = q.where(Mark.source == source)
        return [dict(as_of=a, value=v, source=src) for a, v, src in s.execute(q).all()]


def search_documents(query, kinds=None, limit=5, max_chars=1800):
    with Session() as s:
        if IS_PG:
            sql = text("""SELECT id, filename, kind, as_of, source, text,
                                 ts_rank(to_tsvector('english', coalesce(text,'')), plainto_tsquery('english', :q)) AS r
                          FROM documents WHERE to_tsvector('english', coalesce(text,'')) @@ plainto_tsquery('english', :q)
                          """ + ("AND kind = ANY(:kinds) " if kinds else "") + "ORDER BY r DESC, uploaded_at DESC LIMIT :lim")
            params = {"q": query, "lim": limit}
            if kinds: params["kinds"] = kinds
            rows = s.execute(sql, params).all()
            hits = [dict(id=r[0], filename=r[1], kind=r[2], as_of=r[3], source=r[4], text=r[5]) for r in rows]
        else:
            words = [w for w in query.lower().split() if len(w) > 2][:6]
            q = select(Document).order_by(desc(Document.uploaded_at)).limit(400)
            if kinds: q = q.where(Document.kind.in_(kinds))
            docs = s.execute(q).scalars().all()
            scored = []
            for d in docs:
                t = (d.text or "").lower()
                sc = sum(t.count(w) for w in words)
                if sc: scored.append((sc, d))
            scored.sort(key=lambda x: -x[0])
            hits = [dict(id=d.id, filename=d.filename, kind=d.kind, as_of=d.as_of, source=d.source, text=d.text) for _, d in scored[:limit]]
    # trim to the most relevant window of each document
    out = []
    for h in hits:
        t = h["text"] or ""
        lw = t.lower(); pos = min([lw.find(w) for w in query.lower().split() if len(w) > 2 and lw.find(w) >= 0] or [0])
        start = max(0, pos - max_chars // 3)
        h["excerpt"] = t[start:start + max_chars]
        del h["text"]; out.append(h)
    return out


def get_document(doc_id, max_chars=12000):
    with Session() as s:
        d = s.get(Document, doc_id)
        if not d: return None
        return dict(id=d.id, filename=d.filename, kind=d.kind, as_of=d.as_of, source=d.source, text=(d.text or "")[:max_chars], meta=d.meta)


def positions(status="open"):
    with Session() as s:
        q = select(Position).order_by(Position.updated_at.desc())
        if status: q = q.where(Position.status == status)
        return [dict(id=p.id, name=p.name, side=p.side, instrument=p.instrument, entry=p.entry, size=p.size, stop=p.stop,
                     target=p.target, basis=p.basis, status=p.status, pnl=p.pnl, notes=p.notes, owner=p.owner,
                     updated=p.updated_at.strftime("%Y-%m-%d")) for p in s.execute(q).scalars().all()]


def upsert_position(data: dict):
    with Session() as s:
        p = s.get(Position, data["id"]) if data.get("id") else None
        if not p and data.get("name"):
            p = s.execute(select(Position).where(Position.name == data["name"])).scalars().first()
        if not p:
            p = Position(name=data.get("name", "unnamed")); s.add(p)
        for k in ("name", "side", "instrument", "entry", "size", "stop", "target", "basis", "status", "pnl", "notes", "owner"):
            if k in data and data[k] is not None: setattr(p, k, data[k])
        s.commit(); return p.id


def add_note(date, title, text_):
    with Session() as s:
        s.add(Note(date=date, title=title, text=text_)); s.commit()


def recent_notes(n=10):
    with Session() as s:
        rows = s.execute(select(Note).order_by(desc(Note.date), desc(Note.id)).limit(n)).scalars().all()
        return [dict(date=r.date, title=r.title, text=r.text) for r in rows]


def log_message(user, role, content, tin=0, tout=0, cached=0):
    with Session() as s:
        s.add(Message(user=user, role=role, content=content, tokens_in=tin, tokens_out=tout, cached=cached)); s.commit()


def recent_messages(user, n=8):
    with Session() as s:
        rows = s.execute(select(Message).where(Message.user == user).order_by(desc(Message.id)).limit(n * 2)).scalars().all()
        return [dict(role=r.role, content=r.content) for r in reversed(rows)]


def token_totals():
    with Session() as s:
        r = s.execute(text("SELECT COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0), COALESCE(SUM(cached),0), COUNT(*) FROM messages WHERE role='assistant'")).one()
        return dict(tokens_in=int(r[0]), tokens_out=int(r[1]), cached=int(r[2]), answers=int(r[3]))
