"""Daily cross-asset moves from Platts: crude benchmarks, crude spreads and
refined products vs Dated Brent, with lead-lag correlations and betas."""
import bisect
import concurrent.futures as _cf
import math
import threading
import time
from datetime import date, datetime, timedelta, timezone

HIST_START = "2024-01-01"
TTL = 1800
LAG_WINDOWS = (60, 250)
LAGS = (-2, -1, 0, 1, 2, 3)

# key: (symbol, label, group, unit, bbl_per_mt or None, assessment window)
SERIES = {
    "dated": ("PCAAS00", "Dated Brent", "crude", "$/bbl", None, "London 16:30"),
    "brent1": ("PCAAQ00", "Brent Mo01 (cash)", "crude", "$/bbl", None, "London 16:30"),
    "wti": ("PCACG00", "WTI Cushing Mo01", "crude", "$/bbl", None, "NY 14:30"),
    "dubai": ("PCAAT00", "Dubai Mo01", "crude", "$/bbl", None, "Singapore 16:30"),
    "murban": ("AAKNL00", "Murban Mo01", "crude", "$/bbl", None, "Singapore 16:30"),
    "bd": ("AAJMS00", "Brent Mo01 vs Dubai Mo01", "spread", "$/bbl", None, "Singapore 16:30"),
    "bwti": ("AALAU00", "Brent Mo01 vs WTI Mo01", "spread", "$/bbl", None, "London 16:30"),
    "dfl": ("DBVBM00", "Dated vs Brent Mo01 (DFL proxy)", "spread", "$/bbl", None, "London 16:30"),
    "murdub": ("AARBZ00", "Murban vs Dubai", "spread", "$/bbl", None, "Singapore 16:30"),
    "go": ("AAYWS00", "Gasoil 0.1% CIF NWE", "product", "$/t", 7.45, "London 16:30"),
    "ulsd": ("AAVBG00", "ULSD 10ppm CIF NWE", "product", "$/t", 7.45, "London 16:30"),
    "jet": ("PJAAU00", "Jet CIF NWE", "product", "$/t", 7.88, "London 16:30"),
    "ebob": ("AAQZV00", "Eurobob FOB AR", "product", "$/t", 8.33, "London 16:30"),
    "nap": ("PAAAL00", "Naphtha CIF NWE", "product", "$/t", 8.9, "London 16:30"),
    "fo35": ("PUABC00", "FO 3.5% FOB Rotterdam", "product", "$/t", 6.35, "London 16:30"),
    "sgo": ("AAOVC00", "Gasoil 10ppm FOB Singapore", "product", "$/bbl", None, "Singapore 16:30"),
    "s92": ("PGAEY00", "Gasoline 92 FOB Singapore", "product", "$/bbl", None, "Singapore 16:30"),
    "s380": ("PPXDK00", "FO 380 CST FOB Singapore", "product", "$/t", 6.35, "Singapore 16:30"),
}

_lock = threading.Lock()
_cache = {"t": 0.0, "payload": None}


def _fetch(get, sym):
    out, page = {}, 1
    filt = f'symbol: "{sym}" AND bate:"c" AND assessDate >= "{HIST_START}"'
    while True:
        j = get("/market-data/v3/value/history/symbol", {"filter": filt, "pageSize": 10000, "page": page})
        for r in j.get("results", []):
            for d in r.get("data", []):
                if d.get("value") is not None and d.get("assessDate"):
                    out[d["assessDate"][:10]] = float(d["value"])
        if page >= int((j.get("metadata") or {}).get("totalPages") or 1):
            return out
        page += 1


def _diffs(a, b, lag=0):
    """Paired daily changes: change in a on day i with change in b on day i+lag (common dates)."""
    xs, ys = [], []
    for i in range(1, len(a)):
        j = i + lag
        if 1 <= j < len(b) and a[i] is not None and a[i - 1] is not None and b[j] is not None and b[j - 1] is not None:
            xs.append(a[i] - a[i - 1])
            ys.append(b[j] - b[j - 1])
    return xs, ys


def _corr_beta(xs, ys):
    n = len(xs)
    if n < 15:
        return None, None, n
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None, None, n
    return sxy / math.sqrt(sxx * syy), sxy / sxx, n


def _r(v, n=3):
    return None if v is None else round(v, n)


def _on_or_before(ds, vs, iso):
    i = bisect.bisect_right(ds, iso) - 1
    return (vs[i], ds[i]) if i >= 0 else (None, None)


def build_payload(get):
    with _cf.ThreadPoolExecutor(8) as ex:
        hist = dict(zip(SERIES, ex.map(lambda k: _fetch(get, SERIES[k][0]), SERIES)))
    for k, (_, _, grp, _, f, _) in SERIES.items():
        if grp == "product":
            dated = hist["dated"]
            conv = {d: (v / f if f else v) for d, v in hist[k].items()}
            hist[k + "_bbl"] = conv
            hist[k + "_crk"] = {d: v - dated[d] for d, v in conv.items() if d in dated}
    hist["wtidub"] = {d: hist["bd"][d] - hist["bwti"][d] for d in hist["bd"] if d in hist["bwti"]}
    dates = sorted(hist["dated"])
    as_of = dates[-1]
    cal = sorted({d for h in hist.values() for d in h})

    def col(k):
        h = hist[k]
        return [h.get(d) for d in cal]

    def stats(k):
        h = hist[k]
        ds = sorted(h)
        if not ds:
            return {"status": "missing"}
        vs = [h[d] for d in ds]
        ld = date.fromisoformat(ds[-1])
        out = {"date": ds[-1], "value": vs[-1], "dod": vs[-1] - vs[-2] if len(vs) > 1 else None,
               "stale": (date.fromisoformat(as_of) - ld).days > 4}
        for tag, days in (("wow", 7), ("mom", 30), ("m3", 91)):
            p, _ = _on_or_before(ds, vs, (ld - timedelta(days=days)).isoformat())
            out[tag] = None if p is None else vs[-1] - p
        return out

    ref = col("dated")
    lag_keys = ["brent1", "wti", "dubai", "murban", "bd", "bwti", "dfl"] + \
        [k + "_bbl" for k, s in SERIES.items() if s[2] == "product"] + [k + "_crk" for k, s in SERIES.items() if s[2] == "product"]
    lags = {}
    for k in lag_keys:
        c = col(k)
        lags[k] = {}
        for w in LAG_WINDOWS:
            a, b = ref[-(w + 4):], c[-(w + 4):]
            row = {}
            for L in LAGS:
                r, beta, n = _corr_beta(*_diffs(a, b, L))
                row[str(L)] = {"r": _r(r), "beta": _r(beta), "n": n}
            lags[k][str(w)] = row

    mkeys = ["dated", "brent1", "wti", "dubai", "murban", "bd", "bwti", "dfl", "go_bbl", "jet_bbl",
             "ebob_bbl", "nap_bbl", "fo35_bbl", "sgo_bbl", "s92_bbl", "s380_bbl", "go_crk", "ebob_crk"]
    cols = {k: col(k)[-64:] for k in mkeys}
    corr = [[_r(_corr_beta(*_diffs(cols[a], cols[b]))[0], 2) for b in mkeys] for a in mkeys]

    roll = []
    bd, dfl = col("bd"), col("dfl")
    for i in range(60, len(cal)):
        r, _, n = _corr_beta(*_diffs(bd[i - 60:i + 1], dfl[i - 60:i + 1]))
        roll.append([cal[i], _r(r, 2)])

    names = {k: s[1] for k, s in SERIES.items()}
    for k, s in SERIES.items():
        if s[2] == "product":
            names[k + "_bbl"] = s[1] + " ($/bbl)"
            names[k + "_crk"] = s[1].split(" (")[0] + " crack vs Dated"
    names["wtidub"] = "WTI vs Dubai (derived)"
    keep = list(SERIES) + [k for k in hist if k.endswith("_bbl") or k.endswith("_crk")] + ["wtidub"]
    return {
        "source": "platts", "as_of": as_of,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "meta": {k: {"symbol": s[0], "label": s[1], "group": s[2], "unit": s[3], "bbl_per_mt": s[4], "window": s[5]} for k, s in SERIES.items()},
        "names": names,
        "series": {k: {"dates": sorted(hist[k]), "values": [hist[k][d] for d in sorted(hist[k])]} for k in keep},
        "stats": {k: stats(k) for k in keep},
        "lags": lags, "lag_windows": list(LAG_WINDOWS), "lag_list": list(LAGS),
        "corr": {"keys": mkeys, "m": corr, "ndays": 63},
        "bd_dfl_roll60": roll,
    }


def get_payload(get, refresh=False):
    with _lock:
        if not refresh and _cache["payload"] and time.time() - _cache["t"] < TTL:
            return _cache["payload"]
        p = build_payload(get)
        _cache.update(t=time.time(), payload=p)
        return p


def cached_payload():
    return _cache["payload"]
