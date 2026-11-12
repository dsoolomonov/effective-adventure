"""4:30pm Singapore indicative curve parser. Values in $/bbl. Sections: EFS, DUBAI (intermonths), BRENT DUBAI, DFL,
DATED/DUB, DATED SPD, MURBAN/DUB, MRB/BRENT. Computes both triangle identities and the Dubai J/F box check."""
import re

SECTIONS = {"efs": "efs", "dubai": "dub", "brent dubai": "bd", "dfl": "dfl", "dated/dub": "datdub", "dated spd": "dtd",
            "murban/dub": "murdub", "mrb/brent": "murbrent", "murban/brent": "murbrent"}


def _key(label):
    l = label.strip().lower().replace("'", "")
    m = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)-?(\d{2})?$", l)
    if m: return m.group(1)
    if re.match(r"^q[1-4]$", l): return l
    if "/" in l: return l.replace("/", "")          # N/D -> nd, Dec/Dec -> decdec, Nov/Dec -> novdec
    return re.sub(r"[^a-z0-9]", "", l)


def parse(text, as_of):
    marks, sec = {}, None
    for raw in text.splitlines():
        line = raw.strip().replace("\t", " ")
        if not line: continue
        low = line.lower()
        hit = [v for k, v in SECTIONS.items() if low == k or low.startswith(k + " ") and not re.search(r"\d", low)]
        if hit and not re.search(r"-?\d+\.\d+", line):
            sec = hit[0]; continue
        if sec is None: continue
        m = re.match(r"^([A-Za-z/'\-0-9 ]+?)\s+(-?\d+(?:\.\d+)?)\s*$", line)
        if not m: continue
        key = sec + "." + _key(m.group(1)); val = float(m.group(2))
        marks[key] = val
    d = marks
    # identities
    for mo in ("nov", "dec", "jan", "feb"):
        if all(k in d for k in (f"dfl.{mo}", f"bd.{mo}", f"datdub.{mo}")):
            marks[f"derived.triangle_{mo}"] = round(d[f"datdub.{mo}"] - (d[f"dfl.{mo}"] + d[f"bd.{mo}"]), 2)
    for mo in ("jan", "feb", "mar"):
        if all(k in d for k in (f"murbrent.{mo}", f"efs.{mo}", f"murdub.{mo}")):
            marks[f"derived.murban_id_{mo}"] = round(d[f"murdub.{mo}"] - (d[f"murbrent.{mo}"] + d[f"efs.{mo}"]), 2)
    if "bd.jan" in d and "bd.feb" in d:
        marks["derived.bd_box_janfeb"] = round(d["bd.jan"] - d["bd.feb"], 2)   # Dubai J/F = Brent Mar/Apr - this
    unit = {k: "$" for k in marks}
    return "sing_curve", as_of, marks, unit, {}
