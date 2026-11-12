"""Parsers for the recurring desk inputs. Each returns (kind, as_of, marks:dict, unit_map:dict, meta:dict) or None."""
import re, datetime as dt
from . import morning_run, sing_curve, freight_csv, cot_xlsx


def classify(filename: str, text: str) -> str:
    f = (filename or "").lower(); t = (text or "")[:4000]
    tl = t.lower()
    if f.endswith(".csv") and "source,periodtype,date,instrument" in tl: return "freight_csv"
    if f.endswith((".xlsx", ".xls")) and ("managed money|long" in tl.replace(" | ", "|") or "request_name is ice" in tl or re.match(r"data[ _]\d+", f)): return "cot_xlsx"
    if f.endswith((".xlsx", ".xls", ".xlsm")): return "workbook"
    if f.endswith((".docx", ".pptx")): return "document"
    if f.endswith((".png", ".jpg", ".jpeg")): return "image"
    if f.endswith(".pdf"): return "research"
    if "indicative curve" in tl or ("efs" in tl and "dated/dub" in tl and "murban/dub" in tl): return "sing_curve"
    if "morning run" in tl or ("cfd" in tl and "dfl" in tl and "dtd rolls" in tl): return "morning_run"
    if "closing run" in tl: return "morning_run"
    if "oil barometers" in tl: return "barometers"
    if re.search(r"\b(fob|cfr|cif)\b.*\bdtd\b", tl) and len(t) < 600: return "platts_window"
    if "strait of hormuz" in tl and "rystad" in tl: return "research"
    if any(k in tl for k in ("energy aspects", "fge nexanteca", "rystad", "kpler", "j.p. morgan", "leonidas", "claytonidas", "aem morning")): return "research"
    if f.endswith((".png", ".jpg", ".jpeg")): return "image"
    if f.endswith(".pdf"): return "research"
    return "other"


def parse(kind: str, filename: str, text: str, path: str = None, as_of: str = None):
    as_of = as_of or dt.date.today().isoformat()
    if kind == "morning_run": return morning_run.parse(text, as_of)
    if kind == "sing_curve": return sing_curve.parse(text, as_of)
    if kind == "freight_csv": return freight_csv.parse(path or filename, text)
    if kind == "cot_xlsx": return cot_xlsx.parse(path or filename)
    return None
