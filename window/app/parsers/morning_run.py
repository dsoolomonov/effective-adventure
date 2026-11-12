"""London broker Morning/Closing Run parser.

Expected blocks (order free):
  ICE Brent / ICE Futs:  Jan/Feb: +221/+223   Feb/Mar: +191/+193   Mar/Apr +163/+165   Jun'27/Dec'27: +592/+593
  CFD:  16-20/11 Jan +30 (-85)   30/11-4/12 Jan +145 (+20)   7-11/12 Jan +165 (+50)
  EFP:  Jan +6  Feb +10
  DTD Rolls: Bal Nov/Dec -54   Dec/Jan +253   Jan/Feb +195
  DFL:  Bal Nov +70  Dec +345  Jan +275  Feb +243  1Q'27 +241  2Q'27 +176  3Q'27 +139  Cal'27 +167  Cal'28 +63
  Jan EFS +395
  Dec B/D Swap -1   Jan B/D Swap -28   Feb B/D Swap -37
  Dec Dated/Dubai +344  Jan Dated/Dubai +247  Feb Dated/Dubai +206
Values in cents/bbl. Bid/ask pairs are averaged. Everything else on the tape is kept as text.
"""
import re

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
NUM = r"([+-]?\s?\d+(?:\.\d+)?)"


def _num(s):
    return float(s.replace(" ", "").replace("+", ""))


def _pair(s):
    """'+221/+223' -> 222.0 ; '+30' -> 30.0"""
    s = s.strip()
    m = re.match(r"^([+-]?\s?\d+(?:\.\d+)?)\s*/\s*([+-]?\s?\d+(?:\.\d+)?)$", s)
    if m: return (_num(m.group(1)) + _num(m.group(2))) / 2
    m = re.match(r"^([+-]?\s?\d+(?:\.\d+)?)$", s)
    return _num(m.group(1)) if m else None


def parse(text, as_of):
    t = text.replace("’", "'").replace("’", "'")
    marks, meta = {}, {"tape": []}
    # ICE spreads
    for a, b, val in re.findall(r"(Jan|Feb|Mar|Apr|May|Jun'?\d{0,2})\s*/\s*(Feb|Mar|Apr|May|Jun|Dec'?\d{0,2})\s*:?\s*([+-]?\s?\d+(?:\.\d+)?(?:\s*/\s*[+-]?\s?\d+(?:\.\d+)?)?)", t):
        key = "brent." + a[:3].lower() + b[:3].lower()
        if "'" in a or "'" in b: key = "brent.jun27dec27"
        v = _pair(val)
        if v is not None and key not in marks: marks[key] = v
    # CFD windows vs Jan: "16-20/11 Jan +30 (-85)" or "30/11-4/12 Jan +145 (+20)"
    for win, val, roll in re.findall(r"(\d{1,2}(?:/\d{1,2})?-\d{1,2}/\d{1,2})\s+Jan\s+([+-]?\s?\d+)\s*\(([+-]?\s?\d+)\)", t):
        # normalise: "16-20/11" -> "16-20"; "30/11-4/12" -> "30-4"; "7-11/12" -> "7-11d"; "21-25/12" -> "21-25d"
        if "/11-" in win: k = win.split("/11-")[0] + "-" + win.split("/11-")[1].split("/")[0]
        elif win.endswith("/11"): k = win[:-3]
        elif win.endswith("/12"): k = win[:-3] + "d"
        else: k = win
        marks["cfd." + k] = _num(val); marks["cfdroll." + k] = _num(roll)
    # EFP
    for mo, val in re.findall(r"\b(Jan|Feb)\s+([+-]\s?\d+)\s*(?=\n|$)", t):
        if "efp." + mo.lower() not in marks and "EFP" in t: marks["efp." + mo.lower()] = _num(val)
    # DTD rolls
    for lab, val in re.findall(r"(Bal Nov/Dec|Dec/Jan|Jan/Feb|Nov/Dec)\s+([+-]?\s?\d+)\s*(?=\n|$)", t):
        key = "dtd." + lab.lower().replace("bal ", "").replace("/", "")
        if key not in marks: marks[key] = _num(val)
    # DFL strip
    dfl_block = re.search(r"DFL\s*\n(.*?)(?:\n\s*\n|Jan EFS|$)", t, re.S)
    if dfl_block:
        for lab, val in re.findall(r"(Bal Nov|Bal Dec|Dec|Jan|Feb|1Q'?\d{0,2}|2Q'?\d{0,2}|3Q'?\d{0,2}|4Q'?\d{0,2}|Cal'?\d{2})\s+([+-]?\s?\d+)", dfl_block.group(1)):
            k = lab.lower().replace("bal ", "bal").replace("'", "")
            k = {"bal nov": "balnov", "balnov": "balnov"}.get(k, k)
            marks["dfl." + re.sub(r"[^a-z0-9]", "", k)] = _num(val)
    # EFS, B/D, Dated/Dubai
    m = re.search(r"(Jan|Feb)\s+EFS\s*([+-]?\s?\d+)", t)
    if m: marks["efs." + m.group(1).lower()] = _num(m.group(2))
    for mo, val in re.findall(r"(Dec|Jan|Feb|Mar)\s+B/D\s+Swap\s*([+-]?\s?\d+)", t):
        marks["bd." + mo.lower()] = _num(val)
    for mo, val in re.findall(r"(Nov|Dec|Jan|Feb)\s+Dated/Dubai\s*([+-]?\s?\d+)", t):
        marks["datdub." + mo.lower()] = _num(val)
    # tape lines
    for line in t.splitlines():
        if re.search(r"\bv\b.*\d", line) and ("roll" in line.lower() or "DFL" in line or "TRADES" in line.upper() or "ICE" in line):
            meta["tape"].append(line.strip())
    # derived
    jf = marks.get("brent.janfeb"); fm = marks.get("brent.febmar"); ma = marks.get("brent.marapr")
    if jf is not None and "dfl.dec" in marks:
        marks["derived.dec_basis_vs_jan"] = marks["dfl.dec"] - jf
        w = marks
        if all(k in w for k in ("cfd.30-4", "cfd.7-11d", "cfd.14-18d", "cfd.21-25d")):
            strip = (4 * w["cfd.30-4"] + 5 * w["cfd.7-11d"] + 5 * w["cfd.14-18d"] + 5 * w["cfd.21-25d"] + 4 * w["cfd.21-25d"]) / 23.0
            marks["derived.dec_window_strip"] = round(strip, 1)
            marks["derived.dec_dfl_rich"] = round(marks["derived.dec_basis_vs_jan"] - strip, 1)
    if jf is not None and fm is not None and "dfl.jan" in marks:
        marks["derived.jan_dated_vs_jan_fut"] = marks["dfl.jan"] - (jf + fm)
    if jf is not None and "dfl.balnov" in marks and "dfl.dec" in marks:
        marks["derived.id_balnovdec"] = marks["dfl.balnov"] - marks["dfl.dec"] + jf
    if fm is not None and "dfl.dec" in marks and "dfl.jan" in marks:
        marks["derived.id_decjan"] = marks["dfl.dec"] - marks["dfl.jan"] + fm
    if ma is not None and "dfl.jan" in marks and "dfl.feb" in marks:
        marks["derived.id_janfeb"] = marks["dfl.jan"] - marks["dfl.feb"] + ma
    for mo in ("dec", "jan", "feb"):
        if f"dfl.{mo}" in marks and f"bd.{mo}" in marks and f"datdub.{mo}" in marks:
            marks[f"derived.triangle_{mo}"] = round(marks[f"datdub.{mo}"] - (marks[f"dfl.{mo}"] + marks[f"bd.{mo}"]), 1)
    kind = "closing_run" if "closing run" in t.lower() else "morning_run"
    return kind, as_of, marks, {k: "c" for k in marks}, meta
