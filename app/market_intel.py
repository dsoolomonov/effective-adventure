"""
Market Intelligence engine.

Builds a cross-source market snapshot (positioning, pricing, cracks, swaps,
term structure, refinery margins, and — when reachable — flows/outages) and
turns it into product/region market briefings styled like a trading-desk note.

The natural-language briefings are produced by a rule-based generator that reads
real computed signals. If an OpenAI API key is configured, the same context is
handed to the LLM for polished prose; otherwise the deterministic generator is
used. No external dependency is required for the engine to work.
"""
from __future__ import annotations

import os
import math
from datetime import datetime, timezone

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Series signal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _clean(dates, values):
    xs, ys = [], []
    for d, v in zip(dates, values):
        if v is None:
            continue
        try:
            ys.append(float(v))
            xs.append(d)
        except (TypeError, ValueError):
            continue
    return xs, ys


def series_signal(dates, values, label=""):
    """Compute a rich signal snapshot for a single daily time series."""
    xs, ys = _clean(dates, values)
    if not ys:
        return None
    arr = np.asarray(ys, dtype=float)
    last = float(arr[-1])
    dod = float(arr[-1] - arr[-2]) if len(arr) > 1 else 0.0
    wow = float(arr[-1] - arr[-6]) if len(arr) > 5 else dod
    mom = float(arr[-1] - arr[-22]) if len(arr) > 22 else wow
    win = arr[-60:] if len(arr) >= 60 else arr
    lo, hi, mean = float(win.min()), float(win.max()), float(win.mean())
    rng = hi - lo
    pos_in_range = round((last - lo) / rng * 100, 1) if rng else 50.0
    pctile = round(float((arr <= last).sum()) / len(arr) * 100, 1)
    # short trend via 5d vs 20d average slope
    if len(arr) >= 20:
        trend = "rising" if arr[-1] > arr[-5] > arr[-20] else "falling" if arr[-1] < arr[-5] < arr[-20] else (
            "firming" if arr[-1] > arr[-5] else "softening")
    else:
        trend = "rising" if dod > 0 else "falling" if dod < 0 else "flat"
    return {
        "label": label,
        "last": round(last, 3),
        "dod": round(dod, 3),
        "wow": round(wow, 3),
        "mom": round(mom, 3),
        "min60": round(lo, 3),
        "max60": round(hi, 3),
        "mean60": round(mean, 3),
        "pos_in_range": pos_in_range,
        "pctile": pctile,
        "trend": trend,
        "date": xs[-1],
        "at_60d_low": pos_in_range <= 12,
        "at_60d_high": pos_in_range >= 88,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Context assembly
# ─────────────────────────────────────────────────────────────────────────────
def _pricing_index(pricing):
    """(sheet_lower, label) -> series, plus a flat label index for lookups."""
    idx = {}
    for g in pricing.get("groups", []):
        for s in g.get("series", []):
            idx[(g["sheet"].lower(), s["label"])] = s
    return idx


def _sig_from_idx(idx, sheet, label):
    s = idx.get((sheet.lower(), label))
    if not s:
        return None
    return series_signal(s["dates"], s["values"], label)


def _curve_structure(idx, sheet, prefix, n=6):
    """Front vs deferred term structure. Returns m1, m2, m1_m2 and shape."""
    pts = []
    for i in range(1, n + 1):
        s = idx.get((sheet.lower(), f"{prefix}{i}"))
        if s and s["values"]:
            vv = [v for v in s["values"] if v is not None]
            if vv:
                pts.append(float(vv[-1]))
    if len(pts) < 2:
        return None
    m1, m2 = pts[0], pts[1]
    diff = round(m1 - m2, 3)
    shape = "backwardation" if diff > 0.02 else "contango" if diff < -0.02 else "flat"
    return {"m1": round(m1, 3), "m2": round(m2, 3), "m1_m2": diff,
            "front_back": round(pts[0] - pts[-1], 3), "shape": shape, "curve": pts}


def _cot_signal(cot_multi_data, key):
    df = cot_multi_data.get(key)
    if df is None or len(df) == 0:
        return None
    col = "Managed Money|Net"
    if col not in df.columns:
        return None
    nets = df[col].astype(float).values
    valid = nets[~np.isnan(nets)]
    if len(valid) < 5:
        return None
    last = float(valid[-1])
    wow = float(valid[-1] - valid[-2]) if len(valid) > 1 else 0.0
    m4 = float(valid[-1] - valid[-5]) if len(valid) > 5 else wow
    pctile = round(float((valid <= last).sum()) / len(valid) * 100, 1)
    win = valid[-52:] if len(valid) >= 52 else valid
    mean, std = float(win.mean()), float(win.std())
    z = round((last - mean) / std, 2) if std else 0.0
    return {"mm_net": round(last), "wow": round(wow), "chg_4w": round(m4),
            "pctile": pctile, "z": z,
            "stance": "stretched long" if pctile >= 85 else "net long" if last > 0 and pctile >= 55
            else "light/neutral" if abs(pctile - 50) < 15 else "net short" if last < 0 else "moderate"}


def _margin_signals(margins):
    """Latest weekly refinery margins with w/w change and seasonal percentile."""
    from app.main import _season_for, _pct_rank  # lazy to avoid import cycle at load
    dates = margins["dates"]
    seasons = [_season_for(int(d[5:7])) for d in dates]
    out = []
    for m in margins["margins"]:
        vals = m["values"]
        clean = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(clean) < 5:
            continue
        idxs = [i for i, _ in clean]
        cvals = [v for _, v in clean]
        latest_i, latest = idxs[-1], cvals[-1]
        prev = cvals[-2] if len(cvals) > 1 else latest
        w_ago = cvals[-2]
        season = seasons[latest_i]
        season_vals = sorted(cvals[k] for k in range(len(clean)) if seasons[idxs[k]] == season)
        rank_s = _pct_rank(season_vals, latest)
        out.append({
            "name": m.get("name"), "region": m.get("region"),
            "last": round(latest, 2), "wow": round(latest - w_ago, 2),
            "season": season, "seasonal_pctile": rank_s,
        })
    return out


def build_context(cot_multi_data, pricing, margins, extras=None):
    """Assemble the full cross-market snapshot."""
    idx = _pricing_index(pricing)
    ctx = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "flat": {}, "cracks": {}, "swaps": {}, "curve": {}, "cot": {}, "margins": [],
    }
    # Flat prices
    flat_map = {"WTI": ("wti", "CL1"), "Brent": ("brent", "CO1"), "Gasoil": ("gasoil", "QS1"),
                "RBOB": ("rbob", "XB1"), "Dubai": ("dubai crude", "DAT1")}
    for name, (sh, lab) in flat_map.items():
        sig = _sig_from_idx(idx, sh, lab)
        if sig:
            ctx["flat"][name] = sig
    # Term structure
    for name, (sh, pre) in {"WTI": ("wti", "CL"), "Brent": ("brent", "CO"),
                            "Gasoil": ("gasoil", "QS"), "RBOB": ("rbob", "XB"),
                            "Dubai": ("dubai crude", "DAT")}.items():
        cs = _curve_structure(idx, sh, pre)
        if cs:
            ctx["curve"][name] = cs
    # Cracks (front month of each family)
    for lab in ["HO-WTI 1", "RBOB-WTI 1", "GO-Brent 1", "HO-Brent 1", "RBOB-Brent 1", "HOGO 1"]:
        sig = _sig_from_idx(idx, "cracks", lab)
        if sig:
            ctx["cracks"][lab] = sig
    # Swaps (balmo / M1)
    swap_labels = ["DslCIFNWE M0", "EBOB M0", "EBOB-Brt M0", "JetCIFNWE M0", "JetNWE-Brt BalMo",
                   "USGC ULSD M0", "ULSD-WTI M0", "USGC Gas M0", "USGCGas-WTI M0", "USGC Jet M0",
                   "SingGO M0", "GO-Dubai M0", "SingJet M0", "GO-Jet Rgrd M0"]
    for lab in swap_labels:
        for sh in ("swaps eur", "swaps us", "swaps asia"):
            sig = _sig_from_idx(idx, sh, lab)
            if sig:
                ctx["swaps"][lab] = sig
                break
    # Positioning
    for k in ["wti", "brent", "gasoil", "rbob"]:
        cs = _cot_signal(cot_multi_data, k)
        if cs:
            ctx["cot"][k] = cs
    # Margins
    try:
        ctx["margins"] = _margin_signals(margins)
    except Exception:
        ctx["margins"] = []
    if extras:
        ctx.update(extras)
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Briefing generation (rule-based) — with optional LLM polish
# ─────────────────────────────────────────────────────────────────────────────
REGION_LABEL = {"US": "US", "UK": "UK/Europe", "DUBAI": "Dubai", "SING": "Singapore"}
PRODUCTS = ["crude", "distillate", "gasoline", "freight"]


def _fmt(v, unit="", plus=False):
    if v is None:
        return "n/a"
    s = f"{v:+.2f}" if plus else f"{v:.2f}"
    return f"{s}{unit}"


def _dir_word(x, up="firmer", dn="weaker", flat="little changed"):
    if x is None:
        return flat
    if x > 0.01:
        return up
    if x < -0.01:
        return dn
    return flat


def _pick_crude(ctx, region):
    if region == "US":
        return "WTI", ctx["flat"].get("WTI"), ctx["curve"].get("WTI"), ctx["cot"].get("wti")
    if region == "UK":
        return "Brent", ctx["flat"].get("Brent"), ctx["curve"].get("Brent"), ctx["cot"].get("brent")
    return "Dubai", ctx["flat"].get("Dubai"), ctx["curve"].get("Dubai"), ctx["cot"].get("brent")


def _region_margins(ctx, region):
    want = {"US": "US Gulf Coast", "UK": "North-West Europe", "DUBAI": "Singapore", "SING": "Singapore"}[region]
    return [m for m in ctx.get("margins", []) if m["region"] == want]


def _tldr_line(text):
    return text


def _crude_brief(ctx, region):
    name, flat, curve, cot = _pick_crude(ctx, region)
    if not flat:
        return None
    mgs = _region_margins(ctx, region)
    mg = mgs[0] if mgs else None
    tldr = []
    lead = (f"{name} ${flat['last']:.2f}, {_dir_word(flat['wow'],'up','down')} "
            f"{abs(flat['wow']):.2f} w/w ({flat['trend']}); "
            f"{'front-end '+curve['shape'] if curve else 'curve flat'}.")
    tldr.append(lead)
    if curve:
        tldr.append(f"Term structure in {curve['shape']} (M1-M2 {curve['m1_m2']:+.2f}), "
                    f"{'signalling prompt tightness' if curve['shape']=='backwardation' else 'pointing to prompt length' if curve['shape']=='contango' else 'balanced prompt'}.")
    if cot:
        tldr.append(f"Managed money {cot['stance']} at {cot['pctile']:.0f}th pctile "
                    f"(net {cot['mm_net']:,}, {cot['chg_4w']:+,} over 4wk) — "
                    f"{'crowded, reversal-prone' if cot['pctile']>=85 else 'squeeze risk' if cot['pctile']<=15 else 'room to add'}.")
    if mg:
        tldr.append(f"{region} cracking margin {mg['name']} ${mg['last']:.2f} ({mg['wow']:+.2f} w/w), "
                    f"{mg['seasonal_pctile']:.0f}th seasonal pctile — "
                    f"{'refiners well-incentivised' if mg['seasonal_pctile']>60 else 'margin support fading'}.")

    market_state = (
        f"{name} settled ${flat['last']:.2f}, {_dir_word(flat['dod'],'up','down')} {abs(flat['dod']):.2f} d/d and "
        f"{_dir_word(flat['wow'],'up','down')} {abs(flat['wow']):.2f} w/w, sitting at the {flat['pos_in_range']:.0f}% mark of "
        f"its 60-day range (${flat['min60']:.2f}-${flat['max60']:.2f}). Momentum is {flat['trend']}. "
        + (f"The curve is in {curve['shape']} with M1-M2 at {curve['m1_m2']:+.2f} and front-to-M6 at {curve['front_back']:+.2f}; "
           f"{'prompt scarcity is bid' if curve['shape']=='backwardation' else 'prompt length is weighing on the front' if curve['shape']=='contango' else 'the prompt is balanced'}. " if curve else "")
        + (f"Speculative positioning is {cot['stance']} (MM net {cot['mm_net']:,}, {cot['pctile']:.0f}th pctile, z {cot['z']:+.2f}); "
           f"the 4-week change of {cot['chg_4w']:+,} shows {'fresh length being added' if cot['chg_4w']>0 else 'length being trimmed' if cot['chg_4w']<0 else 'flat flows'}. " if cot else "")
    )

    physical = []
    if mgs:
        best = max(mgs, key=lambda m: m["seasonal_pctile"] or 0)
        physical.append(
            f"Refining economics: {region} margins are led by {best['name']} at ${best['last']:.2f} "
            f"({best['wow']:+.2f} w/w, {best['seasonal_pctile']:.0f}th seasonal pctile). "
            f"{'Strong margins keep crude demand from refiners supported.' if (best['seasonal_pctile'] or 0)>55 else 'Soft margins argue for run cuts and weaker crude pull.'}")
    # relative value vs other benchmarks
    others = {k: v for k, v in ctx["flat"].items() if k in ("WTI", "Brent", "Dubai") and k != name}
    for ok, ov in others.items():
        physical.append(f"{name}-{ok} spread ≈ ${flat['last']-ov['last']:+.2f}; "
                        f"{name} {'at a premium' if flat['last']>ov['last'] else 'at a discount'} to {ok}, "
                        f"{_dir_word(flat['wow']-ov['wow'],'widening','narrowing')} w/w.")

    watch = []
    if curve:
        watch.append(f"Front-spread (M1-M2 {curve['m1_m2']:+.2f}) — a flip "
                     f"{'out of backwardation would confirm prompt easing' if curve['shape']=='backwardation' else 'into backwardation would signal tightening'}.")
    if cot:
        watch.append(f"Positioning extremes — MM at {cot['pctile']:.0f}th pctile; "
                     f"{'watch for long liquidation' if cot['pctile']>=80 else 'watch for short-covering' if cot['pctile']<=20 else 'flows still two-way'}.")
    if mg:
        watch.append(f"Margin sustainability — {mg['name']} at {mg['seasonal_pctile']:.0f}th seasonal pctile; "
                     f"crack compression would remove the refiner bid for crude.")
    watch.append("Flat-price vs physical divergence — geopolitical premia that outrun crack/differential strength tend to fade.")
    return {"tldr": tldr, "market_state": market_state, "physical": physical, "watch": watch,
            "headline_metrics": _crude_metrics(name, flat, curve, cot, mg)}


def _crude_metrics(name, flat, curve, cot, mg):
    out = [{"label": f"{name} flat", "value": f"${flat['last']:.2f}", "chg": f"{flat['wow']:+.2f} w/w"}]
    if curve:
        out.append({"label": "M1-M2", "value": f"{curve['m1_m2']:+.2f}", "chg": curve['shape']})
    if cot:
        out.append({"label": "MM net", "value": f"{cot['mm_net']:,}", "chg": f"{cot['pctile']:.0f}th pctile"})
    if mg:
        out.append({"label": mg['name'], "value": f"${mg['last']:.2f}", "chg": f"{mg['wow']:+.2f} w/w"})
    return out


def _product_brief(ctx, region, product):
    """Distillate / gasoline briefings built from cracks + swaps + positioning."""
    cfg = {
        "distillate": {
            "US": [("USGC ULSD M0", "swaps"), ("ULSD-WTI M0", "crack"), ("HO-WTI 1", "crackc")],
            "UK": [("DslCIFNWE M0", "swaps"), ("GO-Brent 1", "crackc"), ("HOGO 1", "crackc")],
            "DUBAI": [("GO-Dubai M0", "crack"), ("SingGO M0", "swaps")],
            "SING": [("SingGO M0", "swaps"), ("GO-Dubai M0", "crack"), ("GO-Jet Rgrd M0", "crack")],
            "flat": "Gasoil", "cot": "gasoil", "name": "Distillate/Diesel",
        },
        "gasoline": {
            "US": [("USGC Gas M0", "swaps"), ("USGCGas-WTI M0", "crack"), ("RBOB-WTI 1", "crackc")],
            "UK": [("EBOB M0", "swaps"), ("EBOB-Brt M0", "crack"), ("RBOB-Brent 1", "crackc")],
            "DUBAI": [("EBOB M0", "swaps"), ("EBOB-Brt M0", "crack")],
            "SING": [("EBOB M0", "swaps"), ("EBOB-Brt M0", "crack")],
            "flat": "RBOB", "cot": "rbob", "name": "Gasoline",
        },
    }[product]
    items = cfg.get(region, [])
    sigs = []
    for lab, kind in items:
        s = ctx["cracks"].get(lab) or ctx["swaps"].get(lab)
        if s:
            sigs.append((lab, kind, s))
    if not sigs:
        return None
    flat = ctx["flat"].get(cfg["flat"])
    cot = ctx["cot"].get(cfg["cot"])
    # primary crack = first crack-type
    crack = next((s for _, k, s in sigs if k.startswith("crack")), None)
    swap = next((s for _, k, s in sigs if k == "swaps"), None)

    tldr = []
    if crack:
        tldr.append(f"{cfg['name']} crack ({crack['label']}) ${crack['last']:.2f} "
                    f"({crack['wow']:+.2f} w/w, {crack['pctile']:.0f}th pctile) — "
                    f"{'refiners richly paid, watch mean-reversion' if crack['pctile']>=80 else 'crack under pressure, run-cut risk' if crack['pctile']<=20 else 'crack mid-range'}.")
    if swap:
        tldr.append(f"{swap['label']} at {swap['last']:.2f} ({swap['wow']:+.2f} w/w, {swap['trend']}), "
                    f"{swap['pos_in_range']:.0f}% of 60-day range.")
    if flat:
        tldr.append(f"Underlying {cfg['flat']} {flat['last']:.2f} ({flat['wow']:+.2f} w/w) — "
                    f"flat-price {'tailwind' if flat['wow']>0 else 'drag'} on outright product value.")
    if cot:
        tldr.append(f"Positioning proxy ({cfg['cot']}) {cot['stance']} at {cot['pctile']:.0f}th pctile.")

    parts = []
    for lab, kind, s in sigs:
        parts.append(f"{lab} {s['last']:.2f} ({s['wow']:+.2f} w/w, {s['dod']:+.2f} d/d, "
                     f"{s['pos_in_range']:.0f}% of range, {s['trend']})")
    market_state = (f"{REGION_LABEL[region]} {cfg['name'].lower()} complex: " + "; ".join(parts) + ". "
                    + (f"The crack sits at the {crack['pctile']:.0f}th percentile of its own history — "
                       f"{'a level that historically invites refiner selling/hedging' if crack['pctile']>=80 else 'depressed enough to threaten run economics' if crack['pctile']<=20 else 'a neutral level'}. " if crack else "")
                    + (f"Outright {cfg['flat']} is {flat['trend']} at {flat['last']:.2f}. " if flat else ""))

    physical = []
    if crack and flat:
        physical.append(
            f"Crack vs flat: with {cfg['flat']} {flat['trend']} and the crack "
            f"{_dir_word(crack['wow'],'widening','narrowing')} ({crack['wow']:+.2f} w/w), "
            f"{'product is outperforming crude — bullish refining signal' if crack['wow']>0 else 'product is lagging crude — margin squeeze'}.")
    # cross-regional arb hint for the same product
    arb_pairs = {
        "distillate": [("DslCIFNWE M0", "SingGO M0", "NWE vs Sing gasoil (E/W)")],
        "gasoline": [("EBOB M0", "USGC Gas M0", "EBOB vs USGC gasoline (TA arb proxy)")],
    }
    for a, b, lbl in arb_pairs.get(product, []):
        sa, sb = ctx["swaps"].get(a), ctx["swaps"].get(b)
        if sa and sb:
            spread = sa["last"] - sb["last"]
            physical.append(f"{lbl}: {spread:+.2f} ({(sa['wow']-sb['wow']):+.2f} w/w) — "
                            f"{'westbound/transatlantic economics improving' if (sa['wow']-sb['wow'])>0 else 'arb economics deteriorating'}.")

    watch = []
    if crack:
        watch.append(f"{crack['label']} percentile ({crack['pctile']:.0f}th) — crack mean-reversion is the key risk to refiner length.")
    if swap:
        watch.append(f"{swap['label']} momentum ({swap['trend']}) and balmo roll into M1.")
    watch.append("Refinery outages / run cuts (see Cross-Market tab) that could tighten or loosen this product balance.")
    watch.append("Flat-price shocks compressing cracks — the mechanism that breaks refiner economics.")

    metrics = []
    if flat:
        metrics.append({"label": f"{cfg['flat']} flat", "value": f"{flat['last']:.2f}", "chg": f"{flat['wow']:+.2f} w/w"})
    if crack:
        metrics.append({"label": crack['label'], "value": f"{crack['last']:.2f}", "chg": f"{crack['pctile']:.0f}th pctile"})
    if swap:
        metrics.append({"label": swap['label'], "value": f"{swap['last']:.2f}", "chg": f"{swap['wow']:+.2f} w/w"})
    if cot:
        metrics.append({"label": f"{cfg['cot']} MM", "value": f"{cot['mm_net']:,}", "chg": f"{cot['pctile']:.0f}th"})
    return {"tldr": tldr, "market_state": market_state, "physical": physical, "watch": watch,
            "headline_metrics": metrics}


def _freight_brief(ctx, region):
    """Freight note — our dataset lacks direct tanker rates, so we frame freight
    via crude flat-price volatility and curve as a demand-for-transport proxy."""
    crude = ctx["flat"].get("Brent") or ctx["flat"].get("WTI")
    if not crude:
        return None
    tldr = [
        "Direct tanker-rate feeds (TD3c/TD7/TD25) are not in the current dataset — "
        "freight read is inferred from crude flat-price volatility and arb openness.",
        f"Crude flat price is {crude['trend']} ({crude['wow']:+.2f} w/w); "
        f"{'elevated volatility tends to lift war-risk/freight premia' if abs(crude['wow'])>1.5 else 'calm flat price is consistent with soft freight'}.",
    ]
    # arb width proxies (E/W) drive tonne-mile demand
    ew = None
    a, b = ctx["swaps"].get("DslCIFNWE M0"), ctx["swaps"].get("SingGO M0")
    if a and b:
        ew = a["last"] - b["last"]
    market_state = (
        f"Freight is proxied here. Crude sits at {crude['pos_in_range']:.0f}% of its 60-day range with "
        f"{crude['trend']} momentum. "
        + (f"The NWE-Sing gasoil differential (a tonne-mile proxy) is {ew:+.2f}, "
           f"{'supportive of westbound clean tonne-mile demand' if ew and ew>0 else 'soft for clean freight'}. " if ew is not None else "")
        + "For live VLCC/Aframax/clean rates, connect a freight feed (Baltic/Sparta) — the tab is wired to display it when available.")
    physical = [
        "Tonne-mile demand tracks open arbs: wider E/W and transatlantic product spreads pull more long-haul tonnage.",
        "Crude freight (dirty) responds to AG-East flows and Hormuz transit risk; product freight (clean) to NWE↔US↔Asia arbs.",
    ]
    watch = [
        "War-risk insurance repricing around Hormuz — the dominant short-term freight driver.",
        "Arb openness (E/W gasoil, TA gasoline) as the tonne-mile demand signal.",
        "Add a direct freight feed to replace these proxies with TD3c/TD7/TD25/TC2 levels.",
    ]
    metrics = [{"label": "Crude flat", "value": f"{crude['last']:.2f}", "chg": f"{crude['wow']:+.2f} w/w"}]
    if ew is not None:
        metrics.append({"label": "NWE-Sing GO", "value": f"{ew:+.2f}", "chg": "tonne-mile proxy"})
    return {"tldr": tldr, "market_state": market_state, "physical": physical, "watch": watch,
            "headline_metrics": metrics}


def generate_briefing(ctx, product, region):
    product = product.lower()
    region = region.upper()
    if product == "crude":
        body = _crude_brief(ctx, region)
    elif product in ("distillate", "gasoline"):
        body = _product_brief(ctx, region, product)
    elif product == "freight":
        body = _freight_brief(ctx, region)
    else:
        body = None
    if not body:
        return {"available": False, "product": product, "region": region,
                "message": "Insufficient data for this product/region combination."}
    pretty = {"crude": "Crude", "distillate": "Distillate", "gasoline": "Gasoline", "freight": "Freight"}[product]
    date = ctx.get("generated", "")[:10]
    return {
        "available": True,
        "product": product, "region": region,
        "title": f"{region} {pretty} Market Briefing — {date}",
        "date": date,
        "disclaimer": "Generated from platform data (positioning, pricing, cracks, swaps, margins). "
                      "Not investment advice.",
        **body,
        "llm": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Optional LLM polish
# ─────────────────────────────────────────────────────────────────────────────
def _llm_available():
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))


_STYLE = (
    "You are a senior oil trading desk analyst. Write a market-open briefing in the exact "
    "structure: a TL;DR (3-5 punchy lead sentences each followed by a short explanation), "
    "a 'Market State' paragraph, a 'Physical Update' with 2-3 themes, and a numbered 'What to Watch'. "
    "Use ONLY the numbers provided in the JSON context; do not invent figures. Be specific, cite "
    "levels, w/w changes, percentiles, curve shape and positioning. Tone: sharp, non-hedging."
)


def _llm_error():
    """Return a short human-readable reason the LLM isn't producing prose, or None."""
    return getattr(_llm_error, "_last", None)


def _openai_call(user_msg):
    import requests
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
        json={"model": os.environ.get("MARKET_LLM_MODEL", "gpt-4o-mini"),
              "messages": [{"role": "system", "content": _STYLE}, {"role": "user", "content": user_msg}],
              "temperature": 0.4},
        timeout=45)
    if r.status_code != 200:
        _llm_error._last = f"OpenAI {r.status_code}: {r.text[:120]}"
        return None
    return r.json()["choices"][0]["message"]["content"]


def _anthropic_call(user_msg):
    import requests
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        json={"model": os.environ.get("MARKET_LLM_MODEL_ANTHROPIC", "claude-3-5-sonnet-20241022"),
              "max_tokens": 1500, "system": _STYLE,
              "messages": [{"role": "user", "content": user_msg}]},
        timeout=60)
    if r.status_code != 200:
        _llm_error._last = f"Anthropic {r.status_code}: {r.text[:120]}"
        return None
    return r.json()["content"][0]["text"]


def llm_polish_briefing(ctx, product, region, base):
    """If an LLM key exists, rewrite the briefing as flowing desk prose that still
    cites the computed numbers. Falls back to the rule-based note on any error."""
    if not _llm_available():
        return base
    try:
        import json as _json
        user_msg = (f"Product: {product}. Region: {region}.\n"
                    f"Computed signals JSON:\n{_json.dumps(base, default=str)[:6000]}\n"
                    f"Broader context JSON:\n{_json.dumps(ctx, default=str)[:6000]}")
        txt = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            txt = _anthropic_call(user_msg)
        if not txt and os.environ.get("OPENAI_API_KEY"):
            txt = _openai_call(user_msg)
        if not txt:
            return base
        base = dict(base)
        base["prose"] = txt
        base["llm"] = True
        return base
    except Exception as exc:
        _llm_error._last = f"{type(exc).__name__}: {exc}"
        return base
