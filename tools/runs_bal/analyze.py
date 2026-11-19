import json, pathlib, statistics as st
from collections import defaultdict

D = pathlib.Path("/home/ubuntu/runs_bal/data")


def load(s):
    rows = json.loads((D / f"{s}.json").read_text())
    return [(r["p"], float(r["v"])) for r in rows if r["v"] not in (None, "")]


def monthly(s):
    """avg of weekly obs by (year, month)"""
    b = defaultdict(list)
    for p, v in load(s):
        y, m, _ = p.split("-")
        b[(int(y), int(m))].append(v)
    return {k: sum(v) / len(v) for k, v in b.items()}


SER = {
    "p2_runs": "WCRRIP22", "p3_runs": "WCRRIP32", "us_runs": "WCRRIUS2",
    "p2_util": "W_NA_YUP_R20_PER", "p3_util": "W_NA_YUP_R30_PER", "us_util": "WPULEUS3",
    "p2_cap": "W_NA_YRL_R20_MBBLD", "p3_cap": "W_NA_YRL_R30_MBBLD", "us_cap": "WOCLEUS2",
    "p2_gas": "WGFRPP22", "p3_gas": "WGFRPP32", "us_gas": "W_EPM0F_YPR_NUS_MBBLD",
    "p2_dis": "WDIRPP22", "p3_dis": "WDIRPP32", "us_dis": "WDIRPUS2",
    "p2_gstk": "WGTSTP21", "p3_gstk": "WGTSTP31", "us_gstk": "WGTSTUS1",
    "p2_dstk": "WDISTP21", "p3_dstk": "WDISTP31", "us_dstk": "WDISTUS1",
    "us_gdem": "WGFUPUS2", "us_ddem": "WDIUPUS2",
    "us_gexp": "W_EPM0F_EEX_NUS-Z00_MBBLD", "us_dexp": "WDIEXUS2",
    "us_gimp": "WGTIMUS2", "us_dimp": "WDIIMUS2",
    "p2_gi": "WGIRIP22", "p3_gi": "WGIRIP32", "us_gi": "WGIRIUS2",
}
M = {k: monthly(v) for k, v in SER.items()}


def series_month(key, m, years):
    return {y: M[key].get((y, m)) for y in years if M[key].get((y, m)) is not None}


YEARS = range(2015, 2027)
print("=== P2+P3 crude runs, monthly avg (kbd) ===")
print("year  " + "  ".join(f"{m:>6}" for m in range(1, 13)))
for y in YEARS:
    row = []
    for m in range(1, 13):
        a, b = M["p2_runs"].get((y, m)), M["p3_runs"].get((y, m))
        row.append(f"{a+b:6.0f}" if a and b else "     -")
    print(f"{y}  " + "  ".join(row))

print("\n=== P2+P3 implied idle capacity = cap - runs (kbd) ===")
for y in YEARS:
    row = []
    for m in range(1, 13):
        r = [M[k].get((y, m)) for k in ("p2_runs", "p3_runs", "p2_cap", "p3_cap")]
        row.append(f"{r[2]+r[3]-r[0]-r[1]:6.0f}" if all(r) else "     -")
    print(f"{y}  " + "  ".join(row))

print("\n=== P2+P3 utilization on combined capacity (%) ===")
for y in YEARS:
    row = []
    for m in range(1, 13):
        r = [M[k].get((y, m)) for k in ("p2_runs", "p3_runs", "p2_cap", "p3_cap")]
        row.append(f"{100*(r[0]+r[1])/(r[2]+r[3]):6.1f}" if all(r) else "     -")
    print(f"{y}  " + "  ".join(row))

print("\n=== Seasonal step: Aug->Sep and Sep->Oct, P2+P3 runs (kbd) ===")
for y in range(2015, 2026):
    def t(m):
        a, b = M["p2_runs"].get((y, m)), M["p3_runs"].get((y, m))
        return a + b if a and b else None
    aug, sep, oct_, jul = t(8), t(9), t(10), t(7)
    if None in (aug, sep, oct_):
        continue
    print(f"{y}: Jul {jul:6.0f} Aug {aug:6.0f} Sep {sep:6.0f} Oct {oct_:6.0f} | "
          f"Aug->Sep {sep-aug:+6.0f} Sep->Oct {oct_-sep:+6.0f} Aug->Oct {oct_-aug:+6.0f}")

print("\n=== 2026 vs 2025 P2+P3 runs, by month ===")
for m in range(1, 9):
    a = M["p2_runs"].get((2026, m), 0) + M["p3_runs"].get((2026, m), 0)
    b = M["p2_runs"].get((2025, m), 0) + M["p3_runs"].get((2025, m), 0)
    print(f"m{m:02d}: 2026 {a:6.0f}  2025 {b:6.0f}  y/y {a-b:+6.0f}")

print("\n=== US gasoline weekly, last 8 weeks ===")
gas = dict(load("W_EPM0F_YPR_NUS_MBBLD"))
dem = dict(load("WGFUPUS2"))
exp = dict(load("W_EPM0F_EEX_NUS-Z00_MBBLD"))
imp = dict(load("WGTIMUS2"))
stk = dict(load("WGTSTUS1"))
per = sorted(stk)[-9:]
print("week        prod    dem    exp    imp   stocks   d(stk,kb)")
for i in range(1, len(per)):
    p = per[i]
    print(f"{p}  {gas.get(p,0):6.0f} {dem.get(p,0):6.0f} {exp.get(p,0):6.0f} "
          f"{imp.get(p,0):6.0f} {stk[p]:8.0f} {stk[p]-stk[per[i-1]]:+8.0f}")
