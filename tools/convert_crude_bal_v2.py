"""Convert the Crude Balances workbook into a compact JSON for the platform.

One entry per sheet. Each sheet exposes:
  months     : ['YYYY-MM', ...]  (all data columns, chronological)
  groups     : [{code, name, series:{label:[values...]}}]
  order      : per group, ordered list of labels to chart/table (primary first)
  primary    : [{group,label}]   (headline balance/stocks -> first graph)
  analysis   : data-driven 6-month recap + 2-month outlook string
Non-numeric / #REF! / '-' cells become null. Series are trimmed to start at
the first month that actually has data.
"""
import json
import datetime

SRC = "/home/ubuntu/attachments/9d198884-9e29-465d-a1e1-0e462db2e658/Crude+Balances.xlsx"
OUT = "/home/ubuntu/crude-oil-analytics/app/crude_bal_v2.json"
ANCHOR = "2026-07"  # "now" per user (July)

import openpyxl
wb = openpyxl.load_workbook(SRC, data_only=True)


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 3)
    return None


def unit_of(label):
    u = label.lower()
    if "(mb)" in u or " mb" in u:
        return "mb"
    if "utilis" in u or "utiliz" in u or "%" in u or "pct" in u:
        return "ratio"
    return "kb/d"


def date_cols(ws, maxscan=16):
    best_r, best = None, []
    for r in range(1, min(ws.max_row, maxscan) + 1):
        cs = [c for c in range(1, ws.max_column + 1)
              if isinstance(ws.cell(r, c).value, datetime.datetime)]
        if len(cs) > len(best):
            best, best_r = cs, r
    return best_r, best


def months_from(ws, drow, dcols):
    return ["%04d-%02d" % (ws.cell(drow, c).value.year, ws.cell(drow, c).value.month)
            for c in dcols]


def monotonic(months, dcols):
    """Keep only the leading strictly-increasing run of months (some sheets
    append a second date block for a secondary table)."""
    keep = 1
    while keep < len(months) and months[keep] > months[keep - 1]:
        keep += 1
    return months[:keep], dcols[:keep]


def row_series(ws, r, dcols):
    return [num(ws.cell(r, c).value) for c in dcols]


def trim(months, series_map):
    """Drop leading months where every listed series is null."""
    n = len(months)
    first = n
    for vals in series_map.values():
        for i, v in enumerate(vals):
            if v is not None:
                first = min(first, i)
                break
    if first >= n:
        first = 0
    return months[first:], {k: v[first:] for k, v in series_map.items()}


def analysis(months, primary, unit, region, supply=None, runs=None,
             invert=False, stock=False):
    """Build a 6-month recap + 2-month outlook from the primary series."""
    try:
        a = months.index(ANCHOR)
    except ValueError:
        a = len(months) - 3
    def avg(seq):
        xs = [x for x in seq if x is not None]
        return sum(xs) / len(xs) if xs else None
    fmt = (lambda x: "%.0f kb/d" % x) if unit == "kb/d" else (
        (lambda x: "%.0f mb" % x) if unit == "mb" else (lambda x: "%.0f%%" % (x * 100)))
    recent = avg(primary[max(0, a - 6):a])          # last 6 months (actual)
    prior = avg(primary[max(0, a - 12):max(0, a - 6)])
    latest = next((primary[i] for i in range(a - 1, -1, -1)
                   if primary[i] is not None), None)
    fut = avg(primary[a + 1:a + 3])                  # next 2 months (fcst)
    parts = []
    if recent is not None:
        if stock:
            trend = ("built" if (prior is not None and recent > prior) else
                     "drawn" if prior is not None else "held")
            parts.append("Over the past six months %s crude stocks have %s, "
                         "averaging %s (latest %s)." %
                         (region, trend, fmt(recent),
                          fmt(latest) if latest is not None else "n/a"))
        else:
            state = "surplus" if recent > 0 else "deficit"
            if invert:
                state = "deficit" if recent > 0 else "surplus"
            parts.append("Over the past six months the %s crude balance has "
                         "averaged %s — a %s regime (latest %s)." %
                         (region, fmt(recent), state,
                          fmt(latest) if latest is not None else "n/a"))
        if prior is not None:
            delta = recent - prior
            dirn = "wider/looser" if delta > 0 else "tighter"
            if stock:
                dirn = "faster builds" if delta > 0 else "faster draws"
            parts.append("That is %s than the prior six months (%s), i.e. %s." %
                         ("higher" if delta > 0 else "lower", fmt(prior), dirn))
    why = []
    if supply is not None:
        sr = avg(supply[max(0, a - 6):a]); sp = avg(supply[max(0, a - 12):max(0, a - 6)])
        if sr is not None and sp is not None:
            why.append("supply %s" % ("rising" if sr > sp else "easing"))
    if runs is not None:
        rr = avg(runs[max(0, a - 6):a]); rp = avg(runs[max(0, a - 12):max(0, a - 6)])
        if rr is not None and rp is not None:
            why.append("refinery runs %s" % ("climbing" if rr > rp else "softening"))
    if why:
        parts.append("Drivers: " + " and ".join(why) + ".")
    base = latest if latest is not None else recent
    if fut is not None and base is not None:
        d = fut - base
        if stock:
            outlook = "further builds" if d > 0 else "further draws" if d < 0 else "little net change"
        else:
            outlook = "loosening" if d > 0 else "tightening" if d < 0 else "a steady balance"
        parts.append("For the next two months the model points to %s "
                     "(≈ %s), reflecting the seasonal run and trade profile." %
                     (outlook, fmt(fut)))
    return " ".join(parts)


# ---- regional-style sheets (label in col A) -------------------------------
REGIONAL = {
    "Med Balances": ("med", "Mediterranean", "TOTAL BALANCE"),
    "NWE balances": ("nwe", "NW Europe", "TOTAL BALANCE"),
    "Asia Balnces": ("asia", "Asia", "TOTAL BALANCE (adjusted)"),
    "South America Balances": ("sam", "South America", "TOTAL BALANCE"),
}
REG_ORDER = ["TOTAL BALANCE", "TOTAL BALANCE (adjusted)", "SWEET BALANCE",
             "SOUR BALANCE", "RUNS", "UTILISATION",
             "TOTAL SWEET LOAD./PROD.", "TOTAL SOUR LOAD./PROD.",
             "TOTAL SWEET IMPORTS", "TOTAL SOUR IMPORTS",
             "TOTAL SWEET EXPORTS", "TOTAL SOUR EXPORTS",
             "AVAILABLE CAPACITY", "BUILT CAPACITY (CRUDE+COND.)"]

# ---- production-style sheets (Middle East / West Africa) ------------------
PRODSHEETS = {
    "AG Balances": ("ag", "Middle East (AG)", "ADJUSTED BALANCES",
                    ["ADJUSTED BALANCES", "TOTAL BALANCE",
                     "TOTAL CRUDE OIL PRODUCTION", "TOTAL COND. PRODUCTION",
                     "RUNS", "UTILISATION", "TOTAL CRUDE BURN",
                     "TOTAL IMPORTS", "TOTAL SWEET EXPORTS",
                     "TOTAL SOUR EXPORTS", "AVAILABLE CAPACITY"]),
    "West Africa Balances": ("waf", "West Africa", "ADJUSTED BALANCES",
                    ["ADJUSTED BALANCES", "TOTAL BALANCE",
                     "TOTAL AFRICAN CRUDE PRODUCTION",
                     "TOTAL AFRICAN CONDENSATE PRODUCTION",
                     "RUNS", "UTILISATION", "TOTAL IMPORTS",
                     "TOTAL SWEET EXPORTS", "TOTAL SOUR EXPORTS",
                     "AVAILABLE CAPACITY"]),
}

sheets_out = []


def build_labelcol(ws, wanted, drow, dcols):
    """Collect the wanted labels (exact colA match) -> values."""
    found = {}
    for r in range(1, ws.max_row + 1):
        lab = ws.cell(r, 1).value
        if isinstance(lab, str) and lab.strip() in wanted and lab.strip() not in found:
            found[lab.strip()] = row_series(ws, r, dcols)
    return found


for name, (sid, region, primary_lbl) in REGIONAL.items():
    ws = wb[name]
    drow, dcols = date_cols(ws)
    months = months_from(ws, drow, dcols)
    months, dcols = monotonic(months, dcols)
    smap = build_labelcol(ws, set(REG_ORDER), drow, dcols)
    order = [l for l in REG_ORDER if l in smap]
    months2, smap = trim(months, {l: smap[l] for l in order})
    series = [{"label": l, "unit": unit_of(l), "values": smap[l]} for l in order]
    an = analysis(months2, smap.get(primary_lbl, []), unit_of(primary_lbl), region,
                  supply=smap.get("TOTAL SWEET LOAD./PROD."),
                  runs=smap.get("RUNS"), invert=False)
    sheets_out.append({"id": sid, "name": region, "kind": "regional",
                       "months": months2,
                       "groups": [{"code": "", "name": region, "series": series}],
                       "order": [{"group": "", "label": l} for l in order],
                       "primary": [{"group": "", "label": primary_lbl}],
                       "analysis": an})


for name, (sid, region, primary_lbl, want) in PRODSHEETS.items():
    ws = wb[name]
    drow, dcols = date_cols(ws)
    months = months_from(ws, drow, dcols)
    months, dcols = monotonic(months, dcols)
    smap = build_labelcol(ws, set(want), drow, dcols)
    order = [l for l in want if l in smap]
    months2, smap = trim(months, {l: smap[l] for l in order})
    series = [{"label": l, "unit": unit_of(l), "values": smap[l]} for l in order]
    prodlbl = next((l for l in order if "PRODUCTION" in l), None)
    an = analysis(months2, smap.get(primary_lbl, []), unit_of(primary_lbl), region,
                  supply=smap.get(prodlbl), runs=smap.get("RUNS"), invert=False)
    sheets_out.append({"id": sid, "name": region, "kind": "regional",
                       "months": months2,
                       "groups": [{"code": "", "name": region, "series": series}],
                       "order": [{"group": "", "label": l} for l in order],
                       "primary": [{"group": "", "label": primary_lbl}],
                       "analysis": an})


# ---- Global sheet ---------------------------------------------------------
def build_global():
    ws = wb["Global Balances"]
    drow, dcols = date_cols(ws)
    months = months_from(ws, drow, dcols)
    months, dcols = monotonic(months, dcols)
    # blocks keyed by the header text in col B; each has region rows below
    blocks = {}  # block_name -> {region: values}
    cur = None
    for r in range(1, ws.max_row + 1):
        lab = ws.cell(r, 2).value
        if not (isinstance(lab, str) and lab.strip()):
            continue
        lab = lab.strip()
        if lab.endswith("BALANCES"):
            cur = lab
            blocks[cur] = {}
        elif cur and lab in ("MED", "NW EUROPE", "TOTAL EUROPE", "ASIA",
                             "UNITED STATES", "GLOBAL"):
            blocks[cur][lab] = row_series(ws, r, dcols)
    # flatten to series "REGION — Total/Sweet/Sour"
    tag = {"TOTAL BALANCES": "Total", "SWEET BALANCES": "Sweet",
           "SOUR BALANCES": "Sour"}
    series, order = [], []
    prio = [("TOTAL BALANCES", "GLOBAL"), ("SWEET BALANCES", "GLOBAL"),
            ("SOUR BALANCES", "GLOBAL"), ("TOTAL BALANCES", "MED"),
            ("TOTAL BALANCES", "TOTAL EUROPE"), ("TOTAL BALANCES", "ASIA"),
            ("TOTAL BALANCES", "UNITED STATES")]
    smap = {}
    for blk, reg in prio:
        if blk in blocks and reg in blocks[blk] and any(
                v not in (None, 0, 0.0) for v in blocks[blk][reg]):
            lbl = "%s — %s" % (reg.title(), tag[blk])
            smap[lbl] = blocks[blk][reg]
            order.append(lbl)
    months2, smap = trim(months, smap)
    for lbl in order:
        series.append({"label": lbl, "unit": "kb/d", "values": smap[lbl]})
    primary_lbl = "Global — Total"
    an = analysis(months2, smap.get(primary_lbl, []), "kb/d", "global", invert=False)
    sheets_out.append({"id": "global", "name": "Global", "kind": "global",
                       "months": months2,
                       "groups": [{"code": "", "name": "Global", "series": series}],
                       "order": [{"group": "", "label": l} for l in order],
                       "primary": [{"group": "", "label": primary_lbl}],
                       "analysis": an})


build_global()


# ---- US sheet -------------------------------------------------------------
def build_us():
    ws = wb["US Balances"]
    drow, dcols = date_cols(ws)
    months = months_from(ws, drow, dcols)
    months, dcols = monotonic(months, dcols)
    gnames = {"US": "United States", "P1": "PADD 1 (East Coast)",
              "P2": "PADD 2 (Midwest)", "P3": "PADD 3 (Gulf Coast)",
              "P4": "PADD 4 (Rockies)", "P5": "PADD 5 (West Coast)",
              "P9": "PADD 9 (ex-SPR)", "CU": "Cushing"}
    gorder = ["US", "P1", "P2", "P3", "P4", "P5", "CU", "P9"]
    metric_order = ["Stocks (mb)", "Balance", "Stock Change (mb)", "Supply",
                    "Demand", "Production", "Imports", "Runs",
                    "Runs Utilization (pct)"]
    cu_order = ["Stocks (mb)", "Balance", "Stock Change (mb)", "(+) Production",
                "(–) Runs", "(+) Receipts", "(–) Deliveries",
                "Stocks Utilization (pct)"]
    groups = {}
    for r in range(1, ws.max_row + 1):
        g = ws.cell(r, 3).value
        m = ws.cell(r, 4).value
        if isinstance(g, str) and g.strip() and isinstance(m, str) and m.strip():
            g = g.strip(); m = m.strip()
            if m == gnames.get(g, "").split(" (")[0] or m.startswith("PADD"):
                continue  # skip the group title row
            groups.setdefault(g, {})[m] = row_series(ws, r, dcols)
    out_groups, order = [], []
    for g in gorder:
        if g not in groups:
            continue
        mo = cu_order if g == "CU" else metric_order
        keep = [m for m in mo if m in groups[g] and any(
            v is not None for v in groups[g][m])]
        series = [{"label": m, "unit": unit_of(m), "values": groups[g][m]}
                  for m in keep]
        out_groups.append({"code": g, "name": gnames.get(g, g), "series": series})
        for m in keep:
            order.append({"group": g, "label": m})
    # trim months to US-group data span
    usmap = {s["label"]: s["values"] for grp in out_groups
             if grp["code"] == "US" for s in grp["series"]}
    an = analysis(months, usmap.get("Stocks (mb)", []), "mb", "US",
                  runs=usmap.get("Runs"), stock=True)
    sheets_out.append({"id": "us", "name": "United States", "kind": "us",
                       "months": months, "groups": out_groups,
                       "group_order": [g["code"] for g in out_groups],
                       "order": order,
                       "primary": [{"group": "US", "label": "Stocks (mb)"},
                                   {"group": "US", "label": "Balance"}],
                       "analysis": an})


build_us()

blob = {"anchor": ANCHOR, "sheets": sheets_out}
with open(OUT, "w") as f:
    json.dump(blob, f, separators=(",", ":"))
print("wrote", OUT)
for s in sheets_out:
    ng = len(s["groups"]); ns = sum(len(g["series"]) for g in s["groups"])
    print("  %-16s months=%d groups=%d series=%d" %
          (s["id"], len(s["months"]), ng, ns))
    print("     analysis:", s["analysis"][:160])
