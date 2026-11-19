import json, pathlib, statistics as st
from collections import defaultdict
from datetime import date

D = pathlib.Path("/home/ubuntu/runs_bal/data")


def load(s):
    return [(r["p"], float(r["v"])) for r in json.loads((D / f"{s}.json").read_text())
            if r["v"] not in (None, "")]


def monthly(s):
    b = defaultdict(list)
    for p, v in load(s):
        y, m, _ = p.split("-")
        b[(int(y), int(m))].append(v)
    return {k: sum(v) / len(v) for k, v in b.items()}


def last_of_month(s):
    """last weekly obs in each month (stock level)"""
    out = {}
    for p, v in load(s):
        y, m, _ = p.split("-")
        out[(int(y), int(m))] = v
    return out


G = {k: monthly(v) for k, v in {
    "gprod": "W_EPM0F_YPR_NUS_MBBLD", "gdem": "WGFUPUS2",
    "gexp": "W_EPM0F_EEX_NUS-Z00_MBBLD", "gimp": "WGTIMUS2",
    "dprod": "WDIRPUS2", "ddem": "WDIUPUS2", "dexp": "WDIEXUS2", "dimp": "WDIIMUS2",
    "usruns": "WCRRIUS2", "p2runs": "WCRRIP22", "p3runs": "WCRRIP32",
    "p2gas": "WGFRPP22", "p3gas": "WGFRPP32", "p2dis": "WDIRPP22", "p3dis": "WDIRPP32",
}.items()}
GS = last_of_month("WGTSTUS1")
DS = last_of_month("WDISTUS1")
GS2, GS3 = last_of_month("WGTSTP21"), last_of_month("WGTSTP31")
DS2, DS3 = last_of_month("WDISTP21"), last_of_month("WDISTP31")

print("=== US GASOLINE monthly balance (kbd), Aug/Sep/Oct + stock levels (mb) ===")
print("yr-m   prod  dem   exp  imp  net-bal  stk_eom  d_stk_mb")
for y in range(2018, 2027):
    for m in (8, 9, 10, 11):
        if (y, m) not in G["gprod"]:
            continue
        pr, de, ex, im = (G[k][(y, m)] for k in ("gprod", "gdem", "gexp", "gimp"))
        bal = pr + im - ex - de
        prev = GS.get((y, m - 1) if m > 1 else (y - 1, 12))
        cur = GS.get((y, m))
        d = (cur - prev) / 1000 if prev and cur else float("nan")
        print(f"{y}-{m:02d} {pr:6.0f} {de:5.0f} {ex:5.0f} {im:4.0f} {bal:+7.0f} "
              f"{cur/1000 if cur else 0:8.1f} {d:+8.1f}")

print("\n=== US DISTILLATE monthly balance (kbd) ===")
print("yr-m   prod  dem   exp  imp  net-bal  stk_eom  d_stk_mb")
for y in range(2018, 2027):
    for m in (8, 9, 10, 11):
        if (y, m) not in G["dprod"]:
            continue
        pr, de, ex, im = (G[k][(y, m)] for k in ("dprod", "ddem", "dexp", "dimp"))
        bal = pr + im - ex - de
        prev = DS.get((y, m - 1) if m > 1 else (y - 1, 12))
        cur = DS.get((y, m))
        d = (cur - prev) / 1000 if prev and cur else float("nan")
        print(f"{y}-{m:02d} {pr:6.0f} {de:5.0f} {ex:5.0f} {im:4.0f} {bal:+7.0f} "
              f"{cur/1000 if cur else 0:8.1f} {d:+8.1f}")

print("\n=== Mid-Aug snapshot vs history (latest week each year, week ending ~Aug 14) ===")
gs = dict(load("WGTSTUS1")); ds = dict(load("WDISTUS1"))
gd = dict(load("WGFUPUS2")); dd = dict(load("WDIUPUS2"))
gp = dict(load("W_EPM0F_YPR_NUS_MBBLD")); ge = dict(load("W_EPM0F_EEX_NUS-Z00_MBBLD"))
de_ = dict(load("WDIEXUS2")); dp = dict(load("WDIRPUS2"))
for y in range(2019, 2027):
    cand = [p for p in gs if p.startswith(f"{y}-08") and 10 <= int(p[-2:]) <= 18]
    if not cand:
        continue
    p = cand[0]
    print(f"{p}: gas stk {gs[p]/1000:6.1f}mb  dem {gd[p]:5.0f}  prod {gp[p]:5.0f} exp {ge[p]:5.0f} "
          f"| dis stk {ds[p]/1000:6.1f}mb dem {dd[p]:5.0f} prod {dp[p]:5.0f} exp {de_[p]:5.0f}")

print("\n=== PADD-level stocks mid-Aug (mb) ===")
g2 = dict(load("WGTSTP21")); g3 = dict(load("WGTSTP31"))
d2 = dict(load("WDISTP21")); d3 = dict(load("WDISTP31"))
for y in range(2019, 2027):
    cand = [p for p in g2 if p.startswith(f"{y}-08") and 10 <= int(p[-2:]) <= 18]
    if not cand:
        continue
    p = cand[0]
    print(f"{p}: gas P2 {g2[p]/1000:5.1f} P3 {g3[p]/1000:5.1f} | dis P2 {d2[p]/1000:5.1f} P3 {d3[p]/1000:5.1f}")

print("\n=== yields: gasoline & distillate prod / crude runs (P2, P3, US) monthly 2026 & 2025 ===")
for y in (2025, 2026):
    for m in range(1, 13):
        if (y, m) not in G["p2runs"]:
            continue
        p2y = 100 * G["p2gas"][(y, m)] / G["p2runs"][(y, m)]
        p3y = 100 * G["p3gas"][(y, m)] / G["p3runs"][(y, m)]
        p2d = 100 * G["p2dis"][(y, m)] / G["p2runs"][(y, m)]
        p3d = 100 * G["p3dis"][(y, m)] / G["p3runs"][(y, m)]
        usy = 100 * G["gprod"][(y, m)] / G["usruns"][(y, m)]
        usd = 100 * G["dprod"][(y, m)] / G["usruns"][(y, m)]
        print(f"{y}-{m:02d} gasyield P2 {p2y:5.1f} P3 {p3y:5.1f} US {usy:5.1f} | "
              f"disyield P2 {p2d:5.1f} P3 {p3d:5.1f} US {usd:5.1f}")

print("\n=== Sep/Oct US gasoline demand & exports history (kbd) ===")
for y in range(2018, 2026):
    print(f"{y}: dem Sep {G['gdem'][(y,9)]:5.0f} Oct {G['gdem'][(y,10)]:5.0f} | "
          f"exp Sep {G['gexp'][(y,9)]:5.0f} Oct {G['gexp'][(y,10)]:5.0f} | "
          f"dexp Sep {G['dexp'][(y,9)]:5.0f} Oct {G['dexp'][(y,10)]:5.0f} | "
          f"ddem Sep {G['ddem'][(y,9)]:5.0f} Oct {G['ddem'][(y,10)]:5.0f}")
