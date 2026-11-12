"""Per-cargo Dated curve: constrained least-squares smooth daily curve vs Jan futures.
Same method as the desk workbook (v99-v114): minimise ||x - x0||^2 + 0.15*||D2 x||^2 subject to window/average constraints,
solved via KKT. x0 = previous solution (carried in state), realised days frozen.
Inputs are cents/bbl vs Jan. Returns weekly levels, rolls, identities and an xlsx path."""
import json, os, datetime as dt
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from ..config import DATA_DIR

STATE = os.path.join(DATA_DIR, "dated_curve.json")
WINDOWS = {  # key -> (start, end) 2026 dates
    "9-13": (dt.date(2026, 11, 9), dt.date(2026, 11, 13)), "16-20": (dt.date(2026, 11, 16), dt.date(2026, 11, 20)),
    "23-27": (dt.date(2026, 11, 23), dt.date(2026, 11, 27)), "30-4": (dt.date(2026, 11, 30), dt.date(2026, 12, 4)),
    "7-11d": (dt.date(2026, 12, 7), dt.date(2026, 12, 11)), "14-18d": (dt.date(2026, 12, 14), dt.date(2026, 12, 18)),
    "21-25d": (dt.date(2026, 12, 21), dt.date(2026, 12, 25)), "28-31d": (dt.date(2026, 12, 28), dt.date(2026, 12, 31)),
}


def _bdays(a, b):
    d = a; out = []
    while d <= b:
        if d.weekday() < 5: out.append(d)
        d += dt.timedelta(days=1)
    return out


def load_prev():
    if os.path.exists(STATE):
        j = json.load(open(STATE)); return {dt.date.fromisoformat(k): v for k, v in j.items()}
    # cold start: flat prior
    return {d: 0.0 for d in _bdays(dt.date(2026, 9, 21), dt.date(2027, 1, 29))}


def solve(marks: dict, as_of: str, realized_through=dt.date(2026, 10, 30), smooth=0.15):
    prev = load_prev(); dates = sorted(prev); x0 = np.array([prev[d] for d in dates]); n = len(x0)
    idx = {d: i for i, d in enumerate(dates)}
    cons = []
    def avg(a, b, t):
        ii = [idx[d] for d in _bdays(a, b) if d in idx]
        if ii: cons.append((ii, [1 / len(ii)] * len(ii), float(t)))
    as_of_d = dt.date.fromisoformat(as_of[:10])
    jf = marks.get("brent.janfeb")
    if "dfl.balnov" in marks:
        avg(max(as_of_d, dt.date(2026, 11, 2)), dt.date(2026, 11, 30), marks["dfl.balnov"])
    for k, (a, b) in WINDOWS.items():
        if f"cfd.{k}" in marks: avg(a, b, marks[f"cfd.{k}"])
    if jf is not None and "dfl.dec" in marks:
        avg(dt.date(2026, 12, 1), dt.date(2026, 12, 31), marks["dfl.dec"] - jf)
    for d in dates:
        if d <= realized_through: cons.append(([idx[d]], [1.0], x0[idx[d]]))
    m = len(cons); C = np.zeros((m, n)); dv = np.zeros(m)
    for k, (ii, ww, t) in enumerate(cons):
        for i, w in zip(ii, ww): C[k, i] = w
        dv[k] = t
    H2 = np.zeros((n, n))
    for i in range(1, n - 1):
        v = np.zeros(n); v[i - 1] = 1; v[i] = -2; v[i + 1] = 1; H2 += np.outer(v, v)
    H = np.eye(n) + smooth * H2
    KKT = np.block([[2 * H, C.T], [C, np.zeros((m, m))]])
    x = np.linalg.lstsq(KKT, np.concatenate([2 * x0, dv]), rcond=None)[0][:n]
    json.dump({d.isoformat(): float(v) for d, v in zip(dates, x)}, open(STATE, "w"), indent=1)
    weeks = {}
    w = dt.date(2026, 9, 21)
    while w <= dt.date(2027, 1, 25):
        ii = [idx[d] for d in _bdays(w, w + dt.timedelta(days=4)) if d in idx]
        if ii: weeks[w.isoformat()] = round(float(np.mean(x[ii])), 1)
        w += dt.timedelta(days=7)
    wk = list(weeks.items()); rolls = {wk[i][0]: round(wk[i][1] - wk[i + 1][1], 1) for i in range(len(wk) - 1)}
    out = {"as_of": as_of, "weeks": weeks, "rolls": rolls, "dec_basis_vs_jan": (marks.get("dfl.dec") - jf) if jf is not None and "dfl.dec" in marks else None}
    return out, {d.isoformat(): round(float(v), 1) for d, v in zip(dates, x)}


def write_workbook(marks, as_of, res, daily, note, out_dir=None):
    out_dir = out_dir or os.path.join(DATA_DIR, "files"); os.makedirs(out_dir, exist_ok=True)
    wb = Workbook(); ws = wb.active; ws.title = "RUN"
    hdr = Font(bold=True, color="FFFFFF"); fill = PatternFill("solid", fgColor="1F3864")
    ws["A1"] = f"Per-cargo Dated model vs Jan | {as_of} | This document is AI generated"; ws["A1"].font = Font(bold=True)
    ws["A2"] = note; ws["A2"].alignment = Alignment(wrap_text=True, vertical="top"); ws.merge_cells("A2:H2"); ws.row_dimensions[2].height = 160
    r = 4
    for j, h in enumerate(("Mark", "Value", "Unit"), 1): c = ws.cell(r, j); c.value = h; c.font = hdr; c.fill = fill
    for k in sorted(marks):
        r += 1; ws.cell(r, 1).value = k; ws.cell(r, 2).value = marks[k]; ws.cell(r, 3).value = "c vs Jan" if k.startswith(("cfd", "dfl", "dtd", "efs", "bd", "datdub")) else ""
    r += 2
    for j, h in enumerate(("Week start", "Level vs Jan", "Roll to next"), 1): c = ws.cell(r, j); c.value = h; c.font = hdr; c.fill = fill
    for wstart, lv in res["weeks"].items():
        r += 1; ws.cell(r, 1).value = wstart; ws.cell(r, 2).value = lv; ws.cell(r, 3).value = res["rolls"].get(wstart)
    wd = wb.create_sheet("DAILY"); wd["A1"] = "Date"; wd["B1"] = "Smooth level vs Jan (c/bbl)"
    for i, (d, v) in enumerate(daily.items(), 2): wd.cell(i, 1).value = d; wd.cell(i, 2).value = v
    ws.column_dimensions["A"].width = 34; ws.column_dimensions["B"].width = 14; ws.column_dimensions["C"].width = 14
    path = os.path.join(out_dir, f"percargo_{as_of.replace(':', '').replace(' ', '_')}.xlsx"); wb.save(path); return path
