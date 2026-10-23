"""Live weekly oil-stock hubs from the Platts/SPGCI API.

Builds the Product Stocks payload (per-hub product histories + a regional
summary in mmb with w/w, y/y and vs the 2017-19 same-week average) and a
feed of the latest Platts stocks articles.
"""
import bisect
import concurrent.futures as _cf
import html as _html
import re
import threading
import time
from datetime import date, datetime, timedelta

HIST_START = "2016-01-01"
TTL = 1800
STALE_DAYS = 28
BASE_YEARS = (2017, 2018, 2019)

# barrels per tonne used to express ARA (kt) in mmb
BBL_PER_T = {"gasoline": 8.45, "naphtha": 8.9, "jet": 7.88, "gasoil": 7.46, "fueloil": 6.66}

# (name, symbol, Platts description, factor to the region display unit)
REGIONS = [
    {"id": "us", "name": "US", "unit": "mmbbl", "source": "EIA WPSR via Platts", "products": [
        ("Gasoline", "EIABC00", "EIA 1 MoGas US Stks", 1),
        ("Distillate fuel oil", "EIABH00", "EIA 1 Dist FO US Stks", 1),
        ("Jet/kero", "EIABG00", "EIA 1 Jet Kero US Stks", 1),
        ("Residual fuel oil", "EIABL00", "EIA 1 Resid FO US Stks", 1),
        ("Crude (commercial ex-SPR)", "EIAWA00", "EIA 9 Crude Comml US Stks Excluding Lease Stocks", 1),
        ("Crude — Cushing", "EIAHW00", "EIA 9 Crude Comml Cushing OK Stks", 1),
        ("Crude — SPR", "EIABQ00", "EIA 1 Crude in SPR US Stks", 1),
    ]},
    {"id": "ara", "name": "ARA", "unit": "kt", "source": "Insights Global via Platts", "products": [
        ("Light ends", "ARSTL04", "Insights Global Light-ends ARA Stocks Weekly", 1),
        ("Gasoline", "ARSTG04", "Insights Global Gasoline ARA Stocks Weekly", 1),
        ("Naphtha", "ARSTN04", "Insights Global Naphtha ARA Stocks Weekly", 1),
        ("Middle distillates", "ARSTM04", "Insights Global Middle Distillates ARA Stocks Weekly", 1),
        ("Gasoil", "ARSTO04", "Insights Global Gasoil ARA Stocks Weekly", 1),
        ("Jet/kero", "ARSTJ04", "Insights Global Jet Kero ARA Stocks Weekly", 1),
        ("Fuel oil", "ARSTF04", "Insights Global Fuel Oil ARA Stocks Weekly", 1),
        ("Residuals", "ARSTR04", "Insights Global Residuals ARA Stocks Weekly", 1),
    ]},
    {"id": "singapore", "name": "Singapore", "unit": "mmbbl", "source": "Enterprise Singapore via Platts", "products": [
        ("Light distillates", "SSGP199", "Enterprise Singapore Lt Distillates Singapore Stocks", 1e-3),
        ("Middle distillates", "SSGP229", "Enterprise Singapore Mid Distillates Singapore Stocks", 1e-3),
        ("Residues", "SSGP599", "Enterprise Singapore Residues Singapore Stocks", 1e-3),
    ]},
    {"id": "japan", "name": "Japan", "unit": "mmbbl", "source": "PAJ via Platts", "products": [
        ("Crude", "AAVQZ00", "PAJ Crude Stks Wkly Bbl", 1e-6),
        ("Gasoline", "AALNX00", "PAJ Gasoline Prod Stks Wkly Bbl", 1e-6),
        ("Gasoil", "AALNZ00", "PAJ Gasoil Prod Stks Wkly Bbl", 1e-6),
        ("Kerosene", "AALQU00", "PAJ Kero Prod Stks Wkly Bbl", 1e-6),
        ("Jet", "AALNY00", "PAJ Jet Prod Stks Wkly Bbl", 1e-6),
        ("Fuel oil", "AALOF00", "PAJ FO Prod Stks Wkly Bbl", 1e-6),
        ("HSFO", "AALOE00", "PAJ HSFO Prod Stks Wkly Bbl", 1e-6),
        ("LSFO", "AALOD00", "PAJ LSFO Prod Stks Wkly Bbl", 1e-6),
    ]},
    {"id": "fujairah", "name": "Fujairah", "unit": "mmbbl", "source": "FEDCom / S&P Global via Platts", "products": [
        ("Light distillates", "FUJLD04", "FEDCom Platts Fujairah Light Distillates Stocks Volume", 1e-3),
        ("Middle distillates", "FUJMD04", "FEDCom Platts Fujairah Middle Distillates Stocks Volume", 1e-3),
        ("Heavy distillates & residues", "FUJHD04", "FEDCom Platts Fujairah Heavy Distillates and Residues Stocks Volume", 1e-3),
    ]},
]

GROUPS = [("light", "Light distillates"), ("middle", "Middle distillates"), ("fo", "Fuel oil"), ("crude", "Crude")]
_K = 1e-3  # kt x bbl/t -> mmb

# summary rows: {group: [(symbol, factor to mmb), ...]} ; missing group = no series
SUMMARY_ROWS = [
    {"id": "us", "name": "US", "kind": "region", "cells": {
        "light": [("EIABC00", 1)], "middle": [("EIABH00", 1), ("EIABG00", 1)],
        "fo": [("EIABL00", 1)], "crude": [("EIAWA00", 1)]}},
    *[{"id": f"padd{n}", "name": f"PADD {n}", "kind": "sub", "cells": {
        "light": [(g, 1)], "middle": [(d, 1), (j, 1)], "fo": [(r, 1)], "crude": [(c, 1)]}}
      for n, g, d, j, r, c in [
          (1, "EIAIC00", "EIALY00", "EIALS00", "EIANI00", "EIAWB00"),
          (2, "EIAIG00", "EIAMC00", "EIALT00", "EIANM00", "EIAWC00")]],
    {"id": "cushing", "name": "Cushing", "kind": "subsub", "cells": {"crude": [("EIAHW00", 1)]}},
    *[{"id": f"padd{n}", "name": f"PADD {n}", "kind": "sub", "cells": {
        "light": [(g, 1)], "middle": [(d, 1), (j, 1)], "fo": [(r, 1)], "crude": [(c, 1)]}}
      for n, g, d, j, r, c in [
          (3, "EIAIH00", "EIAMD00", "EIALU00", "EIANN00", "EIAWE00"),
          (4, "EIAII00", "EIAME00", "EIALV00", "EIANO00", "EIAWF00"),
          (5, "EIAIJ00", "EIAMF00", "EIALW00", "EIANP00", "EIAWI00")]],
    {"id": "ara", "name": "ARA", "kind": "region", "cells": {
        "light": [("ARSTG04", BBL_PER_T["gasoline"] * _K), ("ARSTN04", BBL_PER_T["naphtha"] * _K)],
        "middle": [("ARSTO04", BBL_PER_T["gasoil"] * _K), ("ARSTJ04", BBL_PER_T["jet"] * _K)],
        "fo": [("ARSTF04", BBL_PER_T["fueloil"] * _K)]}},
    {"id": "singapore", "name": "Singapore", "kind": "region", "cells": {
        "light": [("SSGP199", 1e-3)], "middle": [("SSGP229", 1e-3)], "fo": [("SSGP599", 1e-3)]}},
    {"id": "japan", "name": "Japan", "kind": "region", "cells": {
        "light": [("AALNX00", 1e-6)], "middle": [("AALNZ00", 1e-6), ("AALQU00", 1e-6), ("AALNY00", 1e-6)],
        "fo": [("AALOF00", 1e-6)], "crude": [("AAVQZ00", 1e-6)]}},
    {"id": "fujairah", "name": "Fujairah", "kind": "region", "cells": {
        "light": [("FUJLD04", 1e-3)], "middle": [("FUJMD04", 1e-3)], "fo": [("FUJHD04", 1e-3)]}},
]
TOTALS = [("total", "Total 5", ["us", "ara", "singapore", "japan", "fujairah"]),
          ("wos", "WoS", ["us", "ara"]),
          ("eos", "EoS", ["singapore", "japan", "fujairah"])]
SPR = ("EIABQ00", 1)

NOT_AVAILABLE = {
    ("ara", "crude"): "No ARA crude stock series on Platts",
    ("singapore", "crude"): "No Singapore crude stock series on Platts",
    ("fujairah", "crude"): "No Fujairah crude stock series on Platts",
}

NEWS_QUERIES = ["stocks", "stockpiles", "inventories", "ARA oil product stocks", "Fujairah stocks",
                "Enterprise Singapore stocks", "EIA inventories", "crude stocks", "Oil Stock"]
NEWS_RE = re.compile(
    r"oil product stock|oil stock|inventory (tracker|update)"
    r"|(crude|gasoline|distillate|diesel|gasoil|jet|kerosene|fuel oil|naphtha|resid\w*|product|oil|heavy|light|middle)"
    r"[\w\s,-]{0,25}(stocks|stockpiles|inventor(y|ies))", re.I)
NEWS_EXCLUDE = re.compile(r"xylene|toluene|benzene|styrene|polymer|\bPE\b|\bPP\b|ethylene|propylene|methanol|"
                          r"steel|coal|iron ore|LNG|equit|share price", re.I)
NEWS_TTL = 1200

_lock = threading.Lock()
_cache = {"ts": 0.0, "data": None}
_news_lock = threading.Lock()
_news_cache = {"ts": 0.0, "data": None}


def _all_symbols():
    syms = {s for rg in REGIONS for _, s, _, _ in rg["products"]}
    for row in SUMMARY_ROWS:
        for comps in row["cells"].values():
            syms.update(s for s, _ in comps)
    syms.add(SPR[0])
    return sorted(syms)


def _fetch_batch(get, syms):
    """{symbol: {YYYY-MM-DD: value}} for a batch of symbols (any bate; 'c' preferred)."""
    out, bates = {}, {}
    sym_list = ",".join(f'"{s}"' for s in syms)
    filt = f'symbol IN ({sym_list}) AND assessDate >= "{HIST_START}"'
    page = 1
    while True:
        j = get("/market-data/v3/value/history/symbol", {"filter": filt, "pageSize": 10000, "page": page})
        for r in j.get("results", []):
            s = r.get("symbol")
            for d in r.get("data", []):
                v, ad, b = d.get("value"), d.get("assessDate"), d.get("bate")
                if v is None or not ad:
                    continue
                k = ad[:10]
                if b == "c" or k not in out.get(s, {}) or bates.get((s, k)) != "c":
                    out.setdefault(s, {})[k] = float(v)
                    bates[(s, k)] = b
        if page >= int((j.get("metadata") or {}).get("totalPages") or 1):
            return out
        page += 1


def fetch_history(get):
    syms = _all_symbols()
    batches = [syms[i:i + 8] for i in range(0, len(syms), 8)]
    hist = {}
    with _cf.ThreadPoolExecutor(6) as ex:
        for part in ex.map(lambda b: _fetch_batch(get, b), batches):
            hist.update(part)
    return hist


def _nearest(series_dates, series, target, tol=6):
    """Value of the observation closest to target date within tol days."""
    t = target.isoformat()
    i = bisect.bisect_left(series_dates, t)
    best = None
    for k in (i - 1, i):
        if 0 <= k < len(series_dates):
            dd = abs((date.fromisoformat(series_dates[k]) - target).days)
            if dd <= tol and (best is None or dd < best[0]):
                best = (dd, series[series_dates[k]])
    return None if best is None else best[1]


def _same_day(d, year):
    try:
        return d.replace(year=year)
    except ValueError:
        return d.replace(year=year, day=28)


def series_stats(series, today):
    """latest / w-o-w / 4w / y-o-y / vs 2017-19 same-week average for one series."""
    if not series:
        return None
    ds = sorted(series)
    last = ds[-1]
    ld = date.fromisoformat(last)
    v = series[last]
    prev = series[ds[-2]] if len(ds) >= 2 else None
    p4 = series[ds[-5]] if len(ds) >= 5 else None
    ly = _nearest(ds, series, ld - timedelta(days=364))
    base = [b for b in (_nearest(ds, series, _same_day(ld, y)) for y in BASE_YEARS) if b is not None]
    avg = sum(base) / len(base) if base else None
    return {
        "date": last, "value": v,
        "wow": None if prev is None else v - prev,
        "w4": None if p4 is None else v - p4,
        "yoy": None if ly is None else v - ly,
        "avg1719": avg, "vs1719": None if avg is None else v - avg, "base_n": len(base),
        "stale": (today - ld).days > STALE_DAYS,
    }


def _cell(hist, comps, today):
    parts = []
    for s, f in comps:
        st = series_stats(hist.get(s), today)
        if st is None:
            return {"status": "missing", "symbols": [s for s, _ in comps]}
        parts.append((st, f))
    stale = [p for p in parts if p[0]["stale"]]
    syms = [s for s, _ in comps]
    if stale:
        return {"status": "stale", "symbols": syms, "last": min(p[0]["date"] for p in stale)}
    out = {"status": "ok", "symbols": syms, "date": max(p[0]["date"] for p in parts),
           "base_n": min(p[0]["base_n"] for p in parts)}
    for k in ("value", "wow", "yoy", "vs1719"):
        vals = [p[0][k] for p in parts]
        out[k] = None if any(x is None for x in vals) else round(sum(x * f for x, (_, f) in zip(vals, parts)), 3)
    return out


def _sum_cells(cells):
    ok = [c for c in cells if c and c.get("status") == "ok"]
    if not ok:
        return None
    out = {"status": "ok", "date": max(c["date"] for c in ok), "base_n": min(c.get("base_n", 0) for c in ok)}
    for k in ("value", "wow", "yoy", "vs1719"):
        vals = [c.get(k) for c in ok]
        out[k] = None if any(x is None for x in vals) else round(sum(vals), 3)
    return out


def build_summary(hist, today):
    rows, by_id = [], {}
    for r in SUMMARY_ROWS:
        cells = {}
        for g, _ in GROUPS:
            if g in r["cells"]:
                cells[g] = _cell(hist, r["cells"][g], today)
            elif (r["id"], g) in NOT_AVAILABLE:
                cells[g] = {"status": "na", "note": NOT_AVAILABLE[(r["id"], g)]}
            else:
                cells[g] = None
        row = {"id": r["id"], "name": r["name"], "kind": r["kind"], "cells": cells}
        rows.append(row)
        by_id[r["id"]] = row
    for tid, tname, members in TOTALS:
        cells, incl = {}, {}
        for g, _ in GROUPS:
            mc = [by_id[m]["cells"].get(g) for m in members]
            cells[g] = _sum_cells(mc)
            if cells[g]:
                cells[g]["included"] = [m for m, c in zip(members, mc) if c and c.get("status") == "ok"]
                incl[g] = cells[g]["included"]
        rows.append({"id": tid, "name": tname, "kind": "total", "cells": cells,
                     "members": members})
    spr = _cell(hist, [SPR], today)
    rows.append({"id": "spr", "name": "US SPR", "kind": "spr",
                 "cells": {"light": None, "middle": None, "fo": None, "crude": spr}})
    return rows


def _fmt(v, d=1):
    return "—" if v is None else f"{v:+.{d}f}"


def _region_analysis(rg, prods, today):
    unit = "kt" if rg["unit"] == "kt" else "mmbbl"
    bits, lead = [], []
    for p in prods:
        st = p.get("stats")
        if not st:
            continue
        if st["stale"]:
            bits.append(f"{p['name']}: last Platts print {st['date']} (stale)")
            continue
        base = "vs 2017–19" if st["base_n"] == 3 else f"vs {st['base_n']}y of 2017–19"
        s = (f"{p['name']}: {st['value']:,.1f} {unit} (w/w {_fmt(st['wow'])}, y/y {_fmt(st['yoy'])}, "
             f"{base} {_fmt(st['vs1719'])})")
        bits.append(s)
        lead.append(st["date"])
    head = f"{rg['name']} stocks — latest week {max(lead) if lead else '—'}, {rg['source']}, values in {unit}. "
    return head + " | ".join(bits)


def build_payload(get, today=None):
    today = today or datetime.utcnow().date()
    hist = fetch_history(get)
    regions = []
    for rg in REGIONS:
        prods = []
        for name, sym, desc, f in rg["products"]:
            ser = hist.get(sym) or {}
            ds = sorted(ser)
            conv = {d: ser[d] * f for d in ds}
            st = series_stats(conv, today)
            prods.append({"name": name, "symbol": sym, "description": desc, "dates": ds,
                          "values": [round(conv[d], 4) for d in ds], "stats": st,
                          "stale": bool(st and st["stale"]), "available": bool(ds)})
        regions.append({"id": rg["id"], "name": rg["name"], "unit": rg["unit"], "source": rg["source"],
                        "products": [p for p in prods if p["available"]],
                        "unavailable": [p["name"] + " (" + p["symbol"] + ")" for p in prods if not p["available"]],
                        "stale": [p["name"] + " — last " + p["stats"]["date"] for p in prods if p["stale"]],
                        "analysis": _region_analysis(rg, prods, today)})
    latest = [p["stats"]["date"] for r in regions for p in r["products"] if p["stats"] and not p["stale"]]
    return {
        "as_of": max(latest) if latest else None,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "platts",
        "regions": regions,
        "summary": {"groups": [{"id": g, "name": n} for g, n in GROUPS],
                    "rows": build_summary(hist, today),
                    "bbl_per_t": BBL_PER_T, "base_years": list(BASE_YEARS)},
    }


def get_payload(get, refresh=False):
    with _lock:
        c = _cache["data"]
        if c is not None and not refresh and time.time() - _cache["ts"] < TTL:
            return c
        data = build_payload(get)
        _cache.update(ts=time.time(), data=data)
        return data


def cached_payload():
    return _cache["data"]


_TAG = re.compile(r"<[^>]+>")


def _lead(get, art_id, n_par=2, limit=700):
    try:
        j = get(f"/news-insights/v1/content/{art_id}", {})
    except Exception:
        return None
    body = (((j.get("envelope") or {}).get("content") or {}).get("body")) or ""
    paras = [_html.unescape(_TAG.sub("", p)).strip() for p in re.findall(r"<p>(.*?)</p>", body, re.S)]
    paras = [p for p in paras if p]
    txt = " ".join(paras[:n_par])
    return txt[:limit] + ("…" if len(txt) > limit else "")


def build_news(get, limit=10):
    seen = {}
    for q in NEWS_QUERIES:
        try:
            j = get("/news-insights/v1/search", {"q": q, "pageSize": 40, "sort": "updatedDate:desc"})
        except Exception:
            continue
        for x in j.get("results", []):
            h = x.get("headline") or x.get("title") or ""
            if not NEWS_RE.search(h) or NEWS_EXCLUDE.search(h):
                continue
            seen.setdefault(x["id"], {"id": x["id"], "headline": h, "updated": x.get("updatedDate"),
                                      "url": x.get("documentUrl")})
    items = sorted(seen.values(), key=lambda a: a["updated"] or "", reverse=True)
    out, heads = [], set()
    for a in items:
        if a["headline"] in heads:
            continue
        heads.add(a["headline"])
        out.append(a)
        if len(out) >= limit:
            break
    with _cf.ThreadPoolExecutor(5) as ex:
        for a, lead in zip(out, ex.map(lambda a: _lead(get, a["id"]), out)):
            a["lead"] = lead
    return {"generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "articles": out}


def get_news(get, refresh=False):
    with _news_lock:
        c = _news_cache["data"]
        if c is not None and not refresh and time.time() - _news_cache["ts"] < NEWS_TTL:
            return c
        data = build_news(get)
        _news_cache.update(ts=time.time(), data=data)
        return data
