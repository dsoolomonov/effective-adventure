"""Live crude differentials vs the Dated Brent strips from the Platts/SPGCI API.

North Sea FOB grades vs the North Sea Dated strip and Med / Black Sea /
Caspian grades vs the Med, BTC and CPC Dated strips, with daily history and
a per-grade stats table (d/d, w/w, m/m, y/y, vs 5-year same-date average).
"""
import bisect
import concurrent.futures as _cf
import threading
import time
from datetime import date, datetime, timedelta

HIST_START = "2016-01-01"
TTL = 1800
STALE_DAYS = 5
FIVE_YEARS = (2021, 2022, 2023, 2024, 2025)

# (grade, symbol, Platts description, shown by default)
GROUPS = [
    {"id": "northsea", "name": "North Sea FOB diffs vs Dated Brent strip", "short": "North Sea", "grades": [
        ("Forties", "AAGWZ00", "Forties FOB North Sea vs North Sea Dtd Strip", True),
        ("Ekofisk", "AAGXB00", "Ekofisk FOB North Sea vs North Sea Dtd Strip", True),
        ("Oseberg", "AAGXF00", "Oseberg FOB North Sea vs North Sea Dtd Strip", True),
        ("Johan Sverdrup", "AJSVB00", "Johan Sverdrup FOB North Sea vs North Sea Dtd Strip", True),
        ("Statfjord", "AAGXD00", "Statfjord FOB Rotterdam vs North Sea Dtd Strip", True),
        ("Midland CIF", "WMCRB00", "WTI Midland CIF Rotterdam vs Fwd Dated Brent", True),
        ("Troll", "AAWEY00", "Troll FOB North Sea vs North Sea Dated Strip", False),
        ("BNB", "AAVJB00", "BNB FOB North Sea vs North Sea Dtd Strip", False),
        ("Grane", "PCALB00", "Grane Blend FOB North Sea vs North Sea Dtd Strip", False),
        ("Flotta Gold", "AAGXH00", "Flotta Gold FOB North Sea vs North Sea Dtd Strip", False),
        ("Ekofisk CIF", "AAHXB00", "Ekofisk CIF Rotterdam vs Fwd Dated Brent", False),
        ("Oseberg CIF", "AAHXD00", "Oseberg CIF Rotterdam vs Fwd Dated Brent", False),
    ]},
    {"id": "med", "name": "Med, Black Sea & Caspian diffs vs Dated Brent strip", "short": "Med / Black Sea / Caspian", "grades": [
        ("CPC", "AAHPL00", "CPC Blend CIF vs CPC Dated Brent Strip", True),
        ("Azeri", "AAHPM00", "Azeri Light CIF Augusta vs BTC Dtd Strip", True),
        ("BTC", "AAUFJ00", "BTC FOB Ceyhan vs BTC Dtd Strip", True),
        ("Saharan", "AAHPN00", "Saharan Blend FOB Algeria vs BTC Dtd Strip", True),
        ("Es Sider", "AAGYH00", "Es Sider FOB Libya vs BTC Dtd Strip", True),
        ("Kirkuk", "AAGYF00", "Kirkuk FOB Ceyhan vs Med Dtd Strip", True),
        ("Urals NWE", "AAGXJ00", "Urals Rotterdam vs Med Dtd Strip", True),
        ("Siberian Light", "AAHPK00", "Siberian Light CIF Augusta vs Med Dtd Strip", False),
        ("CPC FOB Suez", "AALVZ00", "CPC Blend FOB Suez vs CPC Dtd Strip", False),
        ("Suez Blend", "AAGYD00", "Suez Blend FOB Egypt vs Med Dtd Strip", False),
        ("KEBCO CIF Med", "KBCOB00", "Kazakh Export Blend (KEBCO) CIF Med vs Med Dtd Strip", False),
    ]},
]

_lock = threading.Lock()
_cache = {"t": 0.0, "payload": None}


def _symbols():
    return [g[1] for grp in GROUPS for g in grp["grades"]]


def _fetch_batch(get, syms):
    """{symbol: {YYYY-MM-DD: close}} for a batch of symbols."""
    out = {}
    sym_list = ",".join(f'"{s}"' for s in syms)
    filt = f'symbol IN ({sym_list}) AND bate:"c" AND assessDate >= "{HIST_START}"'
    page = 1
    while True:
        j = get("/market-data/v3/value/history/symbol", {"filter": filt, "pageSize": 10000, "page": page})
        for r in j.get("results", []):
            s = r.get("symbol")
            for d in r.get("data", []):
                v, ad = d.get("value"), d.get("assessDate")
                if v is not None and ad:
                    out.setdefault(s, {})[ad[:10]] = float(v)
        if page >= int((j.get("metadata") or {}).get("totalPages") or 1):
            return out
        page += 1


def fetch_history(get):
    syms = _symbols()
    batches = [syms[i:i + 4] for i in range(0, len(syms), 4)]
    hist = {}
    with _cf.ThreadPoolExecutor(6) as ex:
        for part in ex.map(lambda b: _fetch_batch(get, b), batches):
            hist.update(part)
    return hist


def _on_or_before(ds, vs, target, tol=7):
    i = bisect.bisect_right(ds, target.isoformat()) - 1
    if i < 0 or (target - date.fromisoformat(ds[i])).days > tol:
        return None
    return vs[i]


def _same_day(d, year):
    try:
        return d.replace(year=year)
    except ValueError:
        return d.replace(year=year, day=28)


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def grade_stats(ds, vs, as_of):
    if not ds:
        return {"status": "missing"}
    ld = date.fromisoformat(ds[-1])
    v = vs[-1]

    def chg(days):
        p = _on_or_before(ds, vs, ld - timedelta(days=days))
        return None if p is None else v - p

    yr = [x for d, x in zip(ds, vs) if d >= (ld - timedelta(days=365)).isoformat()]
    ytd = [x for d, x in zip(ds, vs) if d[:4] == ds[-1][:4]]
    m1 = [x for d, x in zip(ds, vs) if d > (ld - timedelta(days=30)).isoformat()]
    five = [_on_or_before(ds, vs, _same_day(ld, y), 5) for y in FIVE_YEARS]
    five_n = sum(x is not None for x in five)
    win = sorted(x for d, x in zip(ds, vs) if d >= (ld - timedelta(days=5 * 365)).isoformat())
    hi_i = max(range(len(yr)), key=lambda i: yr[i]) if yr else None
    lo_i = min(range(len(yr)), key=lambda i: yr[i]) if yr else None
    yr_d = [d for d in ds if d >= (ld - timedelta(days=365)).isoformat()]
    avg5 = _avg(five)
    return {
        "status": "stale" if (as_of - ld).days > STALE_DAYS else "ok",
        "date": ds[-1], "value": v,
        "dod": v - vs[-2] if len(vs) > 1 else None,
        "wow": chg(7), "mom": chg(30), "m3": chg(91), "yoy": chg(365),
        "avg30": _avg(m1), "ytd_avg": _avg(ytd),
        "hi52": yr[hi_i] if yr else None, "hi52_date": yr_d[hi_i] if yr else None,
        "lo52": yr[lo_i] if yr else None, "lo52_date": yr_d[lo_i] if yr else None,
        "avg5y": avg5, "vs5y": None if avg5 is None else v - avg5, "five_n": five_n,
        "pctile5y": round(100 * bisect.bisect_right(win, v) / len(win)) if win else None,
    }


def build_payload(get, today=None):
    hist = fetch_history(get)
    all_dates = [max(s) for s in hist.values() if s]
    as_of = date.fromisoformat(max(all_dates)) if all_dates else (today or date.today())
    groups = []
    for grp in GROUPS:
        grades = []
        for name, sym, desc, default in grp["grades"]:
            s = hist.get(sym, {})
            ds = sorted(s)
            vs = [round(s[d], 4) for d in ds]
            grades.append({"name": name, "symbol": sym, "desc": desc, "default": default,
                           "dates": ds, "values": vs, "stats": grade_stats(ds, vs, as_of)})
        groups.append({"id": grp["id"], "name": grp["name"], "short": grp["short"], "grades": grades})
    return {"source": "platts", "as_of": as_of.isoformat(),
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "five_years": list(FIVE_YEARS), "groups": groups}


def get_payload(get, refresh=False):
    with _lock:
        if not refresh and _cache["payload"] and time.time() - _cache["t"] < TTL:
            return _cache["payload"]
        p = build_payload(get)
        _cache.update(t=time.time(), payload=p)
        return p


def cached_payload():
    return _cache["payload"]
