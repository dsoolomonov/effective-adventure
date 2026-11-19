"""Crude Daily Report: live Kpler crude (Crude/Co) flows, oil on water and floating storage.

Sections: US weekly imports/exports, OPEC exports, monthly exports/imports by
country and region, Mideast Gulf + Gulf of Oman daily exports, world oil on
water by current sea area with floating storage.
"""
import json
import os
import threading
import time
from datetime import date, datetime, timedelta

TTL = 3 * 3600
PRODUCT = "Crude/Co"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "crude_daily.json")

# Export table: (label, source, indent). source = Kpler origin country, or ("grade", country, [grades]).
EXPORT_GROUPS = [
    ("OPEC", [
        ("Algeria", "Algeria", 0), ("Congo", "Republic of the Congo", 0), ("Equatorial Guinea", "Equatorial Guinea", 0),
        ("Gabon", "Gabon", 0), ("Iran", "Iran", 0), ("Iraq", "@iraq", 0),
        ("Basrah", "Iraq", 1), ("KRG", ("grade", "Turkey", ["Kirkuk ITP"]), 1),
        ("Kuwait", "Kuwait", 0), ("Libya", "Libya", 0), ("Nigeria", "Nigeria", 0), ("Saudi Arabia", "Saudi Arabia", 0),
        ("S-K Neutral Zone", "Saudi-Kuwaiti Neutral Zone", 0), ("Venezuela", "Venezuela", 0),
    ]),
    ("Rest of Mid East", [("Qatar", "Qatar", 0), ("UAE", "United Arab Emirates", 0), ("Oman", "Oman", 0)]),
    ("North America", [("United States", "United States", 0), ("Canada", "Canada", 0), ("Mexico", "Mexico", 0)]),
    ("FSU", [("Russia", "Russian Federation", 0), ("Kazakhstan", ("grade", "Russian Federation", ["CPC Kazakhstan", "KEBCO"]), 1),
             ("Azerbaijan", ("grade", "Turkey", ["Azeri BTC"]), 0)]),
    ("Europe", [("Norway", "Norway", 0), ("United Kingdom", "United Kingdom", 0)]),
    ("LatAm", [("Brazil", "Brazil", 0), ("Colombia", "Colombia", 0), ("Ecuador", "Ecuador", 0), ("Guyana", "Guyana", 0)]),
    ("APAC (Indonesia)", [("Indonesia", "Indonesia", 0)]),
]
IMPORT_GROUPS = [
    ("Asia", [("China", "China", 0), ("India", "India", 0), ("Japan", "Japan", 0), ("South Korea", "South Korea", 0),
              ("Taiwan", "Taiwan", 0), ("Thailand", "Thailand", 0)]),
    ("North America", [("United States", "United States", 0), ("Canada", "Canada", 0)]),
    ("Europe", [("France", "France", 0), ("Spain", "Spain", 0), ("Italy", "Italy", 0),
                ("Belgium+Netherlands", ["Belgium", "Netherlands"], 0), ("Turkey", "Turkey", 0)]),
]
# Kpler "current seas" -> report region
SEA_REGIONS = [
    ("Mideast Gulf", ["Mideast Gulf"]),
    ("GoO, Arabian, Red", ["Gulf of Oman", "Arabian Sea", "Red Sea", "Gulf of Aden", "Suez Canal"]),
    ("MED Zone, Balt, Casp", ["MED Sea", "Baltic Sea", "Black Sea", "Marmara Sea", "Dardanelles Strait", "Bosphorus Strait",
                              "Caspian Sea", "Volga River", "Don River", "Sea of Azov", "Azov Sea"]),
    ("Indian Ocean", ["West Indian Ocean", "Central Indian Ocean", "East Indian Ocean", "Bay of Bengal", "Andaman Sea", "Mozambique Channel"]),
    ("North Atlantic + Arctic", ["North East Atlantic Ocean", "North West Atlantic Ocean", "North Sea", "Greater ARA", "English Channel",
                                 "Barents Sea", "Norwegian Sea", "Kara Sea", "Irish Sea", "Arctic Ocean", "White Sea", "Celtic Sea", "Bay of Biscay"]),
    ("GoM + Caribs", ["Gulf of Mexico", "Caribbean Sea", "Panama Canal"]),
    ("South Atlantic + WAF", ["South East Atlantic Ocean", "South West Atlantic Ocean", "West African Gulf"]),
    ("Asia Pacific", ["South China Sea", "Eastern China Sea", "Malacca Strait", "Yellow Sea", "Philippine Sea", "Singapore Strait",
                      "North West Pacific Ocean", "Japan Sea", "Gulf of Thailand", "Makassar Strait", "Sulu Sea", "Coral Sea",
                      "Banda Arafura Timor Sea", "South West Pacific Ocean", "Java Sea", "Bohai Sea", "Celebes Sea", "Sea of Okhotsk", "Lombok Strait"]),
    ("Pacific Americas", ["North East Pacific Ocean", "Central East Pacific Ocean", "South East Pacific Ocean"]),
]
PREWAR = ("2025-03-01", "2026-02-28")

_lock = threading.Lock()
_cache = {"t": 0.0, "payload": None, "building": False}


def _clients():
    from kpler.sdk.configuration import Configuration
    from kpler.sdk import Platform
    from kpler.sdk.resources.flows import Flows
    from kpler.sdk.resources.fleet_metrics import FleetMetrics
    u, p = os.environ.get("KPLER_USERNAME", ""), os.environ.get("KPLER_PASSWORD", "")
    if not u or not p:
        raise RuntimeError("Kpler credentials not configured")
    cfg = Configuration(Platform.Liquids, u, p)
    return Flows(cfg), FleetMetrics(cfg)


def _r(v, n=0):
    return None if v is None else round(float(v), n)


def _frame(df):
    df = df.drop(columns=[c for c in ("Period End Date",) if c in df.columns]).copy()
    df["Date"] = df["Date"].astype(str).str[:10]
    return df.set_index("Date").fillna(0.0)


def _month_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) + k
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}-{m:02d}"


def _flows(fl, direction, split, gran, start, end, from_zones=None, to_zones=None, intra=False):
    from kpler.sdk import FlowsDirection, FlowsMeasurementUnit, FlowsPeriod, FlowsSplit
    kw = dict(flow_direction=[getattr(FlowsDirection, direction)], split=[getattr(FlowsSplit, split)],
              granularity=[getattr(FlowsPeriod, gran)], unit=[FlowsMeasurementUnit.KBD], start_date=start, end_date=end,
              with_forecast=False, with_intra_country=intra, products=[PRODUCT])
    if from_zones:
        kw["from_zones"] = from_zones
    if to_zones:
        kw["to_zones"] = to_zones
    return _frame(fl.get(**kw))


def _country_table(groups, base, grades, months, m):
    """Rows with M value, m/m, y/y and 6-month trend for month `m`."""
    def series(src):
        if src == "@iraq":
            return [series("Iraq")[i] + series(("grade", "Turkey", ["Kirkuk ITP"]))[i] for i in range(len(months))]
        if isinstance(src, tuple):
            g = grades[src[1]]
            return [sum(float(g.loc[mo, x]) if mo in g.index and x in g.columns else 0.0 for x in src[2]) for mo in months]
        cols = src if isinstance(src, list) else [src]
        return [sum(float(base.loc[mo, c]) if mo in base.index and c in base.columns else 0.0 for c in cols) for mo in months]

    i = months.index(m)
    iy = months.index(_month_add(m, -12)) if _month_add(m, -12) in months else None

    def row(label, s, indent=0, kind="row"):
        return {"label": label, "kind": kind, "indent": indent, "m": _r(s[i]), "mm": _r(s[i] - s[i - 1]),
                "yy": _r(s[i] - s[iy]) if iy is not None else None, "trend": [_r(x) for x in s[max(0, i - 5):i + 1]],
                "series": [_r(x) for x in s]}

    out, total = [], [0.0] * len(months)
    for gname, members in groups:
        gs = [0.0] * len(months)
        rows = []
        for label, src, indent in members:
            s = series(src)
            rows.append(row(label, s, indent))
            if not indent:
                gs = [a + b for a, b in zip(gs, s)]
        out.append(row(gname, gs, 0, "group"))
        if gname == "OPEC":
            krg = series(("grade", "Turkey", ["Kirkuk ITP"]))
            out.append(row("OPEC (ex-KRG)", [a - b for a, b in zip(gs, krg)], 0, "group"))
        out.extend(rows)
        total = [a + b for a, b in zip(total, gs)]
    out.append(row("Total", total, 0, "total"))
    return out


def _build():
    fl, fm = _clients()
    from kpler.sdk import FleetMetricsAlgo, FleetMetricsMeasurementUnit, FleetMetricsPeriod, FleetMetricsSplit
    today = date.today()
    m_cur = today.strftime("%Y-%m")
    m_last = _month_add(m_cur, -1)
    m0 = _month_add(m_last, -14)
    mstart = date(int(m0[:4]), int(m0[5:7]), 1)
    mend = today
    months = []
    mo = m0
    while mo <= m_last:
        months.append(mo)
        mo = _month_add(mo, 1)
    errors = []
    out = {"generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), "as_of": today.isoformat(), "product": PRODUCT,
           "month": m_last, "months": months, "source": "kpler"}

    def safe(name, f):
        try:
            return f()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {str(e)[:200]}")
            return None

    # monthly exports / imports
    def exports():
        base = _flows(fl, "Export", "OriginCountries", "Monthly", mstart, mend)
        grades = {c: _flows(fl, "Export", "Grades", "Monthly", mstart, mend, from_zones=[c]) for c in ("Turkey", "Russian Federation")}
        rows = _country_table(EXPORT_GROUPS, base, grades, months, m_last)
        opec = next(r for r in rows if r["label"] == "OPEC")
        return rows, {"months": months, "mbd": [None if v is None else round(v / 1000, 2) for v in opec["series"]]}
    ex = safe("exports", exports)
    if ex:
        out["exports"], out["opec_chart"] = ex
    imp = safe("imports", lambda: _country_table(IMPORT_GROUPS, _flows(fl, "Import", "DestinationCountries", "Monthly", mstart, mend), {}, months, m_last))
    if imp:
        out["imports"] = imp

    # US weekly
    def us_weekly():
        ws = today - timedelta(days=70)
        imp_p = _flows(fl, "Import", "DestinationPadds", "EiaWeekly", ws, today + timedelta(days=14), to_zones=["United States"])
        exp_t = _flows(fl, "Export", "Total", "EiaWeekly", ws, today + timedelta(days=14), from_zones=["United States"])
        weeks = [w for w in imp_p.index if w >= (today - timedelta(days=63)).isoformat()]
        cur = next((w for w in weeks if w >= today.isoformat()), weeks[-1])
        weeks = [w for w in weeks if w <= cur][-7:]
        def col(df, names):
            return [_r(sum(float(df.loc[w, c]) for c in names if c in df.columns) if w in df.index else 0.0) for w in weeks]
        padd1 = [c for c in imp_p.columns if c.startswith("PADD 1")]
        rows = [{"label": "Imports", "kind": "total", "s": col(imp_p, list(imp_p.columns))},
                {"label": "PADD 1", "kind": "row", "s": col(imp_p, padd1)},
                {"label": "PADD 2", "kind": "row", "s": col(imp_p, ["PADD 2"])},
                {"label": "PADD 3", "kind": "row", "s": col(imp_p, ["PADD 3"])},
                {"label": "PADD 5", "kind": "row", "s": col(imp_p, ["PADD 5"])},
                {"label": "Exports", "kind": "total", "s": col(exp_t, ["Total"])}]
        res = {"weeks": weeks, "rows": rows}
        oow = fm.get(metric=FleetMetricsAlgo.LoadedVessels, period=FleetMetricsPeriod.Daily, products=[PRODUCT],
                     unit=FleetMetricsMeasurementUnit.BBL, split=FleetMetricsSplit.DestinationCountries,
                     start_date=today - timedelta(days=8), end_date=today)
        if "United States" in oow.columns and len(oow) >= 8:
            v = oow["United States"].astype(float).tolist()
            res["us_bound_on_water"] = {"mb": round(v[-1] / 1e6, 1), "wow": round((v[-1] - v[-8]) / 1e6, 1)}
        return res
    usw = safe("us_weekly", us_weekly)
    if usw:
        out["us_weekly"] = usw

    # Mideast Gulf / Gulf of Oman daily
    def meg():
        s, e = date.fromisoformat(PREWAR[0]), today
        a = _flows(fl, "Export", "OriginCountries", "Daily", s, e, from_zones=["Mideast Gulf"])
        a = a.drop(columns=[c for c in ("Iran",) if c in a.columns])
        b = _flows(fl, "Export", "OriginCountries", "Daily", s, e, from_zones=["Gulf of Oman"])
        b = b.drop(columns=[c for c in ("Iran",) if c in b.columns])
        c = _flows(fl, "Import", "Total", "Daily", s, e, to_zones=["Gulf of Oman"], intra=True)
        days = sorted(set(a.index) | set(b.index))
        hz = [float(a.loc[d].sum()) if d in a.index else 0.0 for d in days]
        goo = [float(b.loc[d].sum()) if d in b.index else 0.0 for d in days]
        gin = [float(c.loc[d, "Total"]) if d in c.index else 0.0 for d in days]
        tot = [x + y for x, y in zip(hz, goo)]
        ma = [sum(tot[max(0, i - 6):i + 1]) / len(tot[max(0, i - 6):i + 1]) for i in range(len(tot))]
        pw = [t for d, t in zip(days, tot) if PREWAR[0] <= d <= PREWAR[1]]
        k = next((i for i, d in enumerate(days) if d >= (today - timedelta(days=70)).isoformat()), 0)
        def lst(v, n=0):
            return [round(x / 1000, 2) for x in v[k:]]
        last7, prev7 = tot[-7:], tot[-14:-7]
        return {"days": days[k:], "hormuz": lst(hz), "goo_loadings": lst(goo), "goo_net": [round((x - y) / 1000, 2) for x, y in zip(goo[k:], gin[k:])],
                "ma7": lst(ma), "prewar_avg": round(sum(pw) / len(pw) / 1000, 2) if pw else None,
                "provisional_from": (today - timedelta(days=14)).isoformat(),
                "stats": {"ma7": round(sum(last7) / 7 / 1000, 2), "ma7_prev": round(sum(prev7) / 7 / 1000, 2),
                          "hormuz7": round(sum(hz[-7:]) / 7 / 1000, 2), "goo7": round(sum(goo[-7:]) / 7 / 1000, 2)}}
    mg = safe("mideast_gulf", meg)
    if mg:
        out["mideast_gulf"] = mg

    # oil on water + floating storage
    def oow():
        s = today - timedelta(days=400)
        d = fm.get(metric=FleetMetricsAlgo.LoadedVessels, period=FleetMetricsPeriod.Daily, products=[PRODUCT],
                   unit=FleetMetricsMeasurementUnit.BBL, split=FleetMetricsSplit.CurrentSeas, start_date=s, end_date=today)
        d = _frame(d)
        fs = _frame(fm.get(metric=FleetMetricsAlgo.FloatingStorage, period=FleetMetricsPeriod.Daily, products=[PRODUCT],
                           unit=FleetMetricsMeasurementUnit.BBL, split=FleetMetricsSplit.Total, floating_storage_duration_min="7",
                           floating_storage_duration_max="Inf", start_date=s, end_date=today))
        days = list(d.index)
        mapped, regions = set(), {}
        for name, seas in SEA_REGIONS:
            cols = [c for c in seas if c in d.columns]
            mapped.update(cols)
            regions[name] = (d[cols].sum(axis=1) / 1e6).tolist() if cols else [0.0] * len(days)
        other = [c for c in d.columns if c not in mapped]
        regions["Others"] = (d[other].sum(axis=1) / 1e6).tolist() if other else [0.0] * len(days)
        world = (d.sum(axis=1) / 1e6).tolist()
        fsv = [float(fs.loc[x, "Total"]) / 1e6 if x in fs.index else None for x in days]

        def ch(v, lag):
            j = len(v) - 1 - lag
            return round(v[-1] - v[j], 1) if j >= 0 and v[j] is not None and v[-1] is not None else None
        def stat(label, v, kind="row"):
            return {"label": label, "kind": kind, "d": round(v[-1], 1), "d1": ch(v, 1), "w1": ch(v, 7), "m1": ch(v, 30), "y1": ch(v, 365)}
        table = [stat("World", world, "total")] + [stat(n, regions[n]) for n in regions] + [stat("Floating storage", fsv, "fs")]
        cut = next((i for i, x in enumerate(days) if x >= (date(today.year - 1, today.month, 1) - timedelta(days=60)).isoformat()), 0)
        return {"date": days[-1], "table": table, "chart": {"days": days[cut:], "regions": {n: [round(x, 1) for x in v[cut:]] for n, v in regions.items()},
                "floating": [None if x is None else round(x, 1) for x in fsv[cut:]]}, "unmapped": other}
    ow = safe("oil_on_water", oow)
    if ow:
        out["oil_on_water"] = ow
    out["errors"] = errors
    out["read"] = _read(out)
    return out


def _fmt(v, n=0, sign=True):
    if v is None:
        return "n/a"
    s = f"{v:+,.{n}f}" if sign else f"{v:,.{n}f}"
    return s


def _read(o):
    """Short desk read built only from the numbers in the payload."""
    lines = []
    ex = {r["label"]: r for r in o.get("exports", [])}
    m = o.get("month")
    if ex.get("OPEC"):
        r, t = ex["OPEC"], ex.get("Total")
        movers = sorted([x for x in o["exports"] if x["kind"] == "row" and x["indent"] == 0 and x["mm"] is not None], key=lambda x: x["mm"])
        up = ", ".join(f"{x['label']} {_fmt(x['mm'])}" for x in movers[::-1][:3] if x["mm"] > 0)
        dn = ", ".join(f"{x['label']} {_fmt(x['mm'])}" for x in movers[:3] if x["mm"] < 0)
        lines.append(f"Exports {m}: OPEC {r['m']/1000:.2f} mb/d ({_fmt(r['mm'])} kb/d m/m, {_fmt(r['yy'])} y/y); tracked total {t['m']/1000:.2f} mb/d ({_fmt(t['mm'])} m/m). "
                     f"Up: {up or 'none'}. Down: {dn or 'none'}.")
    im = {r["label"]: r for r in o.get("imports", [])}
    if im.get("Asia"):
        a, c, i = im["Asia"], im.get("China"), im.get("India")
        lines.append(f"Imports {m}: Asia {a['m']/1000:.2f} mb/d ({_fmt(a['mm'])} m/m, {_fmt(a['yy'])} y/y); China {c['m']:,.0f} ({_fmt(c['mm'])} m/m, {_fmt(c['yy'])} y/y), India {i['m']:,.0f} ({_fmt(i['mm'])} m/m).")
    mg = o.get("mideast_gulf")
    if mg and mg.get("prewar_avg"):
        s = mg["stats"]
        lines.append(f"Mideast Gulf + Gulf of Oman crude exports (ex-Iran): 7-day avg {s['ma7']:.1f} mb/d vs {s['ma7_prev']:.1f} the week before and {mg['prewar_avg']:.1f} pre-war "
                     f"({s['ma7'] - mg['prewar_avg']:+.1f}); inside-Gulf loadings {s['hormuz7']:.1f}, Gulf of Oman {s['goo7']:.1f}.")
    ow = o.get("oil_on_water")
    if ow:
        t = {r["label"]: r for r in ow["table"]}
        w, f = t["World"], t["Floating storage"]
        lines.append(f"Crude on water {w['d']:,.0f} mb ({_fmt(w['w1'])} w/w, {_fmt(w['m1'])} m/m, {_fmt(w['y1'])} y/y); floating storage (7d+) {f['d']:.0f} mb ({_fmt(f['w1'])} w/w).")
    us = o.get("us_weekly")
    if us and len(us["weeks"]) >= 2:
        r = {x["label"]: x for x in us["rows"]}
        lines.append(f"US week to {us['weeks'][-1]} (provisional): imports {r['Imports']['s'][-1]:,.0f} kb/d ({_fmt(r['Imports']['s'][-1] - r['Imports']['s'][-2])} w/w), "
                     f"exports {r['Exports']['s'][-1]:,.0f} ({_fmt(r['Exports']['s'][-1] - r['Exports']['s'][-2])} w/w).")
    return lines


def _load_disk():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _refresh():
    try:
        p = _build()
        ok = any(k in p for k in ("exports", "oil_on_water", "mideast_gulf"))
        if ok:
            with _lock:
                _cache.update(t=time.time(), payload=p)
            try:
                os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
                with open(CACHE_FILE, "w") as f:
                    json.dump(p, f)
            except Exception:  # noqa: BLE001
                pass
        return p
    finally:
        _cache["building"] = False


def get(refresh=False):
    with _lock:
        p, age = _cache["payload"], time.time() - _cache["t"]
    if p is None and not refresh:
        p = _load_disk()
        if p:
            with _lock:
                _cache.update(payload=p, t=0.0)
    if p is not None and not refresh and age < TTL:
        return p
    if p is not None and not refresh:
        if not _cache["building"]:
            _cache["building"] = True
            threading.Thread(target=_refresh, daemon=True).start()
        return dict(p, stale=True)
    _cache["building"] = True
    fresh = _refresh()
    with _lock:
        return _cache["payload"] or fresh
