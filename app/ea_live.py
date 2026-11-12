"""Energy Aspects Data Service: licensed forecasts/balances for the EA tab,
latest release plus the previous release for revision deltas."""
import concurrent.futures as _cf
import json
import os
import threading
import time
import urllib.parse as _up
import urllib.request as _ur
from datetime import datetime, timezone

BASE = "https://api.energyaspects.com/data"
TTL = 6 * 3600
DATE_FROM = "2024-01-01"
PREV_FROM = "2025-06-01"
REVISION_SECTIONS = ("prices", "global", "stocks", "opec", "regional", "products", "margins")
_CFG_PATH = os.path.join(os.path.dirname(__file__), "ea_config.json")

_lock = threading.Lock()
_cache = {"t": 0.0, "payload": None}


def _key():
    k = os.environ.get("EA_API_KEY", "").strip()
    if not k:
        raise RuntimeError("EA_API_KEY not configured")
    return k


def _get(ids, extra=()):
    q = _up.urlencode([("api_key", _key()), ("date_from", DATE_FROM)] + list(extra) + [("dataset_id", i) for i in ids])
    with _ur.urlopen(_ur.Request(BASE + "/timeseries/?" + q, headers={"Accept-Encoding": "identity"}), timeout=120) as r:
        return json.loads(r.read())


def _batches(ids, n=40):
    return [ids[i:i + n] for i in range(0, len(ids), n)]


def build_payload():
    with open(_CFG_PATH) as f:
        cfg = json.load(f)
    all_ids = sorted({i for s in cfg["sections"] for i in s["ids"]})
    series, errors = {}, []

    def pull(b, extra=()):
        try:
            return _get(b, extra)
        except Exception as e:  # one bad batch must not blank the tab
            errors.append(f"{len(b)} series: {e}")
            return []

    with _cf.ThreadPoolExecutor(6) as ex:
        for part in ex.map(pull, _batches(all_ids)):
            for x in part:
                m = x.get("metadata") or {}
                series[str(x["dataset_id"])] = {
                    "release": m.get("release_date"), "fcst_start": m.get("forecast_start_date") or None,
                    "data": x.get("data") or {},
                }
    rev_ids = sorted({i for s in cfg["sections"] if s["key"] in REVISION_SECTIONS for i in s["ids"] if str(i) in series})
    by_rel = {}
    for i in rev_ids:
        rel = (series[str(i)]["release"] or "")[:10]
        if rel:
            by_rel.setdefault(rel, []).append(i)
    jobs = [(b, (("release_date", rel), ("date_from", PREV_FROM))) for rel, ids in by_rel.items() for b in _batches(ids)]
    with _cf.ThreadPoolExecutor(6) as ex:
        for part in ex.map(lambda j: pull(j[0], j[1]), jobs):
            for x in part:
                s = series.get(str(x["dataset_id"]))
                if s is not None:
                    s["prev_release"] = (x.get("metadata") or {}).get("release_date")
                    s["prev"] = x.get("data") or {}
    rels = sorted({s["release"] for s in series.values() if s.get("release")})
    return {
        "source": "energy_aspects", "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_release": rels[-1] if rels else None, "sections": cfg["sections"], "meta": cfg["series"],
        "series": series, "missing": [i for i in all_ids if str(i) not in series], "errors": errors,
    }


def get_payload(refresh=False):
    with _lock:
        if not refresh and _cache["payload"] and time.time() - _cache["t"] < TTL:
            return _cache["payload"]
        p = build_payload()
        _cache.update(t=time.time(), payload=p)
        return p


def cached_payload():
    return _cache["payload"]
