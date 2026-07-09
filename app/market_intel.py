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
# Market news (analyst intel uploaded to app/market_news.txt)
# ─────────────────────────────────────────────────────────────────────────────
_NEWS_PATH = os.path.join(os.path.dirname(__file__), "market_news.txt")

_PRODUCT_KEYWORDS = {
    "crude": ["crude", "brent", "wti", "dubai", "hormuz", "osp", "differential", "cushing",
              "spr", "export", "forties", "angol", "nigeria", "murban", "stockbuild"],
    "distillate": ["diesel", "distillate", "gasoil", "hogo", "jet", "regrade", "ulsd",
                   "heating oil", "yanbu", "gofo", "hydrocracker"],
    "gasoline": ["gasoline", "ebob", "rbob", "sing92", "octane", "reformate", "alkylate",
                 "blend", "naphtha", "gas-nap", "rvo", "rin"],
    "freight": ["freight", "tanker", "vlcc", "aframax", "suezmax", "td3", "td7", "td20",
                "td25", "tc2", "tc5", "tc14", "tonne", "ffa", "charter", "insurance"],
}


def load_market_news():
    try:
        with open(_NEWS_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def news_excerpt(product, limit=9000):
    """Return the paragraphs of the uploaded market news most relevant to a product."""
    txt = load_market_news()
    if not txt:
        return ""
    kws = _PRODUCT_KEYWORDS.get(product.lower(), [])
    paras = [p.strip() for p in txt.split("\n\n") if p.strip()]
    scored = [(sum(p.lower().count(k) for k in kws), p) for p in paras]
    picked = [p for s, p in sorted(scored, key=lambda t: -t[0]) if s > 0] or paras
    out, total = [], 0
    for p in picked:
        if total + len(p) > limit:
            break
        out.append(p)
        total += len(p)
    return "\n\n".join(out)


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
# Term-structure curves (flat, cracks, swaps) + desk trade recommendations
# ─────────────────────────────────────────────────────────────────────────────
def _tenor_pack(idx, sheet, labels, tenor_names=None):
    """Build a term-structure snapshot from a list of tenor labels.

    Returns dict with per-tenor signal, front spread (M1-M2), front-to-back,
    curve shape, and the front-tenor percentile/trend — or None if <2 tenors."""
    rows = []
    for i, lab in enumerate(labels):
        s = _sig_from_idx(idx, sheet, lab)
        if not s:
            continue
        rows.append({
            "tenor": tenor_names[i] if tenor_names else lab,
            "label": lab,
            "last": s["last"], "wow": s["wow"], "dod": s["dod"],
            "pctile": s["pctile"], "trend": s["trend"],
        })
    if len(rows) < 2:
        return None
    m1, m2 = rows[0]["last"], rows[1]["last"]
    diff = round(m1 - m2, 3)
    shape = "backwardation" if diff > 0.02 else "contango" if diff < -0.02 else "flat"
    return {
        "tenors": rows,
        "m1": m1, "m2": m2, "m1_m2": diff,
        "front_back": round(rows[0]["last"] - rows[-1]["last"], 3),
        "shape": shape,
        "front_pctile": rows[0]["pctile"], "front_wow": rows[0]["wow"],
        "front_trend": rows[0]["trend"],
    }


# (family key) -> (sheet, [tenor labels], display name, units)
_FLAT_CURVE_DEFS = {
    "Brent": ("brent", ["CO1", "CO2", "CO3", "CO4", "CO5", "CO6"], "ICE Brent", "$/bbl"),
    "WTI": ("wti", ["CL1", "CL2", "CL3", "CL4", "CL5", "CL6"], "NYMEX WTI", "$/bbl"),
    "Gasoil": ("gasoil", ["QS1", "QS2", "QS3", "QS4", "QS5", "QS6"], "ICE Gasoil", "$/mt"),
    "RBOB": ("rbob", ["XB1", "XB2", "XB3", "XB4", "XB5", "XB6"], "NYMEX RBOB", "¢/gal"),
    "HeatingOil": ("heating oil", ["HO1", "HO2", "HO3", "HO4", "HO5", "HO6"], "NYMEX ULSD (HO)", "¢/gal"),
    "Dubai": ("dubai crude", ["DAT1", "DAT2", "DAT3", "DAT4", "DAT5", "DAT6"], "Dubai", "$/bbl"),
}

_CRACK_CURVE_DEFS = {
    "GO-Brent": ("cracks", ["GO-Brent 1", "GO-Brent 2", "GO-Brent 3", "GO-Brent 4", "GO-Brent 5"],
                 "Gasoil–Brent crack", "$/bbl"),
    "HO-WTI": ("cracks", ["HO-WTI 1", "HO-WTI 2", "HO-WTI 3", "HO-WTI 4", "HO-WTI 5"],
               "ULSD–WTI crack", "$/bbl"),
    "HO-Brent": ("cracks", ["HO-Brent 1", "HO-Brent 2", "HO-Brent 3", "HO-Brent 4"],
                 "ULSD–Brent crack", "$/bbl"),
    "RBOB-Brent": ("cracks", ["RBOB-Brent 1", "RBOB-Brent 2", "RBOB-Brent 3", "RBOB-Brent 4"],
                   "RBOB–Brent crack", "$/bbl"),
    "RBOB-WTI": ("cracks", ["RBOB-WTI 1", "RBOB-WTI 2", "RBOB-WTI 3", "RBOB-WTI 4", "RBOB-WTI 5"],
                 "RBOB–WTI crack", "$/bbl"),
    "HOGO": ("cracks", ["HOGO 1", "HOGO 2", "HOGO 3", "HOGO 4"], "ULSD–Gasoil (HOGO)", "$/bbl"),
}

_SWAP_CURVE_DEFS = {
    "EBOB-Brt": ("swaps eur", ["EBOB-Brt M0", "EBOB-Brt M1", "EBOB-Brt M2", "EBOB-Brt M3", "EBOB-Brt M4"],
                 "EBOB–Brent crack", "$/bbl"),
    "DslCIFNWE": ("swaps eur", ["DslCIFNWE M0", "DslCIFNWE M1", "DslCIFNWE M2", "DslCIFNWE M3", "DslCIFNWE M4"],
                  "Diesel CIF NWE", "$/mt"),
    "JetNWE-Brt": ("swaps eur", ["JetNWE-Brt BalMo", "JetNWE-Brt M1", "JetNWE-Brt M2", "JetNWE-Brt M3", "JetNWE-Brt M4"],
                   "Jet NWE–Brent crack", "$/bbl"),
    "USGCGas-WTI": ("swaps us", ["USGCGas-WTI M0", "USGCGas-WTI M1", "USGCGas-WTI M2", "USGCGas-WTI M3", "USGCGas-WTI M4"],
                    "USGC Gasoline–WTI crack", "$/bbl"),
    "ULSD-WTI": ("swaps us", ["ULSD-WTI M0", "ULSD-WTI M1", "ULSD-WTI M2", "ULSD-WTI M3", "ULSD-WTI M4"],
                 "USGC ULSD–WTI crack", "$/bbl"),
    "GO-Dubai": ("swaps asia", ["GO-Dubai M0", "GO-Dubai M1", "GO-Dubai M2", "GO-Dubai M3", "GO-Dubai M4"],
                 "Sing Gasoil–Dubai crack", "$/bbl"),
    "SingGO": ("swaps asia", ["SingGO M0", "SingGO M1", "SingGO M2", "SingGO M3", "SingGO M4"],
               "Sing Gasoil 10ppm", "$/bbl"),
}


def build_curves(pricing):
    """Full term-structure snapshot for flat benchmarks, cracks and OTC swaps."""
    idx = _pricing_index(pricing)
    tn = ["M1", "M2", "M3", "M4", "M5", "M6"]
    swp_tn = ["M0", "M1", "M2", "M3", "M4"]

    def _collect(defs, tenor_names):
        out = {}
        for key, (sh, labs, disp, units) in defs.items():
            pack = _tenor_pack(idx, sh, labs, tenor_names[:len(labs)])
            if pack:
                pack["display"], pack["units"] = disp, units
                out[key] = pack
        return out

    return {
        "flat": _collect(_FLAT_CURVE_DEFS, tn),
        "cracks": _collect(_CRACK_CURVE_DEFS, tn),
        "swaps": _collect(_SWAP_CURVE_DEFS, swp_tn),
    }


def _stars(conviction):
    conviction = max(1, min(5, int(round(conviction))))
    return "★" * conviction + "☆" * (5 - conviction)


def _bias_from_dir(direction):
    d = direction.upper()
    if "SHORT" in d:
        return "BEARISH"
    if "LONG" in d:
        return "BULLISH"
    return "NEUTRAL"


def _crude_recommendation(name, disp, flat, curve, cot, mg, news_hit):
    """Return a desk trade card for a crude benchmark."""
    if not (flat or curve):
        return None
    score, rationale = 0.0, []
    shape = curve["shape"] if curve else "flat"
    if curve:
        s = 28 if shape == "backwardation" else -28 if shape == "contango" else 0
        score += s
        rationale.append(
            f"Curve in **{shape}** — M1–M2 {curve['m1_m2']:+.2f}, front-to-M6 {curve['front_back']:+.2f} "
            f"({'prompt tightness is bid' if shape == 'backwardation' else 'prompt length weighs on the front' if shape == 'contango' else 'balanced prompt'}).")
    if flat:
        s = max(-18, min(18, flat["wow"] * 6))
        score += s
        rationale.append(
            f"Flat **{disp} ${flat['last']:.2f}**, {'up' if flat['wow'] >= 0 else 'down'} {abs(flat['wow']):.2f} w/w "
            f"({flat['trend']}), {flat['pos_in_range']:.0f}% of the 60-day range.")
    crowded = False
    if cot:
        # contrarian: crowded longs are a headwind
        s = -(cot["pctile"] - 50) * 0.35
        score += s
        crowded = cot["pctile"] >= 82
        light = cot["pctile"] <= 18
        rationale.append(
            f"Managed money **{cot['stance']}** — net {cot['mm_net']:,} ({cot['pctile']:.0f}th pctile, z {cot['z']:+.2f}), "
            f"{cot['chg_4w']:+,} over 4wk. "
            f"{'Crowded long → reversal/liquidation risk.' if crowded else 'Room to add length.' if light else 'Two-way positioning.'}")
    if mg:
        rationale.append(
            f"Refiner pull: {mg['name']} ${mg['last']:.2f} ({mg['seasonal_pctile']:.0f}th seasonal pctile) — "
            f"{'strong margins support crude demand' if (mg['seasonal_pctile'] or 0) > 55 else 'soft margins argue for run cuts'}.")

    score = max(-100, min(100, score))

    # Trade construction
    if shape == "backwardation" and not crowded and score > 0:
        direction, instrument = "LONG", f"Long {disp} M1–M2 time spread + hold prompt length"
        risk = "A flip out of backwardation or a bearish inventory surprise flattens the spread."
        invalidation = f"M1–M2 rolling back below {max(0.0, curve['m1_m2'] - 0.30):+.2f} (loss of backwardation)."
        conv = 4 if score > 45 else 3
    elif shape == "backwardation" and crowded:
        direction, instrument = "NEUTRAL/LONG", f"Book {disp} longs into strength; buy M1–M2 dips, sell flat-price rallies"
        risk = "Crowded MM long can unwind violently even with a firm curve."
        invalidation = "A weekly MM net drop >15% alongside a curve flattening."
        conv = 2
    elif shape == "contango":
        direction, instrument = "SHORT", f"Short {disp} M1–M2 (prompt length) / roll length to deferred"
        risk = "Supply outage or Hormuz escalation snaps the front back into backwardation."
        invalidation = f"M1–M2 recovering above {curve['m1_m2'] + 0.30:+.2f}."
        conv = 3 if score < -35 else 2
    else:
        direction, instrument = "NEUTRAL", f"Stand aside on outright {disp}; trade the M1–M2 range"
        risk = "Low-conviction; a curve break either way sets direction."
        invalidation = "A decisive M1–M2 move (>±0.30) out of the current range."
        conv = 1
    if news_hit:
        conv = min(5, conv + 1)
        rationale.append(f"Market intel corroborates the setup: {news_hit}")

    return {
        "market": disp + " crude", "product": "crude", "benchmark": name,
        "bias": _bias_from_dir(direction), "score": round(score, 1), "conviction": conv, "stars": _stars(conv),
        "direction": direction, "trade": instrument, "rationale": rationale,
        "risk": risk, "invalidation": invalidation,
        "metrics": {
            "flat": f"${flat['last']:.2f}" if flat else "n/a",
            "flat_wow": f"{flat['wow']:+.2f}" if flat else "n/a",
            "m1_m2": f"{curve['m1_m2']:+.2f}" if curve else "n/a",
            "shape": shape,
            "mm_pctile": f"{cot['pctile']:.0f}th" if cot else "n/a",
        },
    }


def _crack_recommendation(cfg, crack_sig, crack_curve, flat, cot, mg, news_hit):
    """Desk card for a product crack (distillate/gasoline/jet)."""
    if not crack_sig:
        return None
    score, rationale = 0.0, []
    pctile = crack_sig["pctile"]
    wow = crack_sig["wow"]
    # momentum
    s = max(-22, min(22, wow * 8))
    score += s
    # level (mean reversion): rich cracks lean bearish forward, cheap cracks bullish
    lvl = (pctile - 50) * -0.45
    score += lvl
    rationale.append(
        f"Crack **{crack_sig['label']} ${crack_sig['last']:.2f}** ({wow:+.2f} w/w, {pctile:.0f}th pctile) — "
        f"{'historically rich, mean-reversion risk' if pctile >= 80 else 'depressed, run-cut/rebound zone' if pctile <= 20 else 'mid-range'}.")
    crk_shape = None
    if crack_curve:
        crk_shape = crack_curve["shape"]
        rationale.append(
            f"Crack curve **{crk_shape}** — M1–M2 {crack_curve['m1_m2']:+.2f} "
            f"({'front crack bid vs deferred (tight prompt product)' if crk_shape == 'backwardation' else 'deferred over prompt (forward strength/weak prompt)' if crk_shape == 'contango' else 'flat crack curve'}).")
        score += 10 if crk_shape == "backwardation" else -8 if crk_shape == "contango" else 0
    if mg:
        s2 = ((mg["seasonal_pctile"] or 50) - 50) * 0.3
        score += s2
        rationale.append(
            f"{cfg['region_name']} margin {mg['name']} ${mg['last']:.2f} ({mg['seasonal_pctile']:.0f}th seasonal pctile, {mg['wow']:+.2f} w/w).")
    if cot:
        rationale.append(f"Positioning proxy ({cfg['cot']}) {cot['stance']} at {cot['pctile']:.0f}th pctile.")

    score = max(-100, min(100, score))
    lab = crack_sig["label"]

    if pctile >= 80:
        direction = "SHORT CRACK"
        instrument = f"Sell/hedge {lab} forward (short M2–M3 crack); book refiner length"
        risk = "Fresh outage or export surge keeps the crack bid despite the rich percentile."
        conv = 4 if pctile >= 92 else 3
        invalidation = f"Crack pushing to a new 60-day high above ${crack_sig['max60']:.2f}."
    elif pctile <= 20:
        direction = "LONG CRACK"
        instrument = f"Long {lab} for mean-reversion (buy prompt crack); run-cut floor near"
        risk = "Demand air-pocket or import wave caps the rebound."
        conv = 4 if pctile <= 8 else 3
        invalidation = f"Crack breaking to a new 60-day low below ${crack_sig['min60']:.2f}."
    elif wow > 0 and (not mg or (mg['seasonal_pctile'] or 0) > 55):
        direction = "LONG CRACK"
        instrument = f"Stay long front {lab}; favour M1–M2 crack backwardation"
        risk = "Flat-price spike compresses the crack; watch crude outperformance."
        conv = 3
        invalidation = f"Crack rolling back below {crack_sig['last'] + crack_sig['wow']:.2f} (this week's base)."
    else:
        direction = "NEUTRAL"
        instrument = f"Range-trade {lab}; no strong edge either way"
        risk = "Low conviction; a percentile break sets direction."
        conv = 1
        invalidation = "A move outside the 20th–80th percentile band."
    if news_hit:
        conv = min(5, conv + 1)
        rationale.append(f"Market intel corroborates: {news_hit}")

    return {
        "market": cfg["market"], "product": cfg["product"], "benchmark": lab,
        "bias": _bias_from_dir(direction), "score": round(score, 1), "conviction": conv, "stars": _stars(conv),
        "direction": direction, "trade": instrument, "rationale": rationale,
        "risk": risk, "invalidation": invalidation,
        "metrics": {
            "crack": f"${crack_sig['last']:.2f}", "crack_wow": f"{wow:+.2f}",
            "crack_pctile": f"{pctile:.0f}th",
            "crack_m1_m2": f"{crack_curve['m1_m2']:+.2f}" if crack_curve else "n/a",
            "crack_shape": crk_shape or "n/a",
            "margin_pctile": f"{mg['seasonal_pctile']:.0f}th" if mg else "n/a",
        },
    }


def _first_crack(ctx, curves, *keys):
    """Return (front-crack signal, crack curve pack) for the first available key."""
    for k in keys:
        cc = curves["cracks"].get(k) or curves["swaps"].get(k)
        sig = None
        # front-crack signal: prefer cracks dict (1) then swaps (M0)
        for lab in (f"{k} 1", f"{k} M0"):
            sig = ctx["cracks"].get(lab) or ctx["swaps"].get(lab)
            if sig:
                break
        if not sig and cc:
            # synthesise a signal-lite from the curve front tenor
            fr = cc["tenors"][0]
            sig = {"label": fr["label"], "last": fr["last"], "wow": fr["wow"],
                   "pctile": fr["pctile"], "trend": fr["trend"],
                   "min60": fr["last"], "max60": fr["last"]}
        if sig:
            return sig, cc
    return None, None


def desk_recommendations(ctx, curves, news_products=None):
    """Build detailed per-market trade recommendations across the barrel."""
    news_products = news_products or {}
    recs = []

    # Crude benchmarks
    crude_defs = [
        ("Brent", "ICE Brent", ctx["flat"].get("Brent"), curves["flat"].get("Brent"), ctx["cot"].get("brent"), "North-West Europe"),
        ("WTI", "NYMEX WTI", ctx["flat"].get("WTI"), curves["flat"].get("WTI"), ctx["cot"].get("wti"), "US Gulf Coast"),
        ("Dubai", "Dubai", ctx["flat"].get("Dubai"), curves["flat"].get("Dubai"), ctx["cot"].get("brent"), "Singapore"),
    ]
    for name, disp, flat, curve, cot, mreg in crude_defs:
        mgs = [m for m in ctx.get("margins", []) if m["region"] == mreg]
        mg = max(mgs, key=lambda m: m["seasonal_pctile"] or 0) if mgs else None
        r = _crude_recommendation(name, disp, flat, curve, cot, mg, news_products.get("crude"))
        if r:
            recs.append(r)

    # Product cracks
    crack_cfgs = [
        {"market": "Distillate — ARA/Gasoil (ICE)", "product": "distillate", "cot": "gasoil",
         "keys": ["GO-Brent"], "region_name": "NW Europe", "margin_region": "North-West Europe"},
        {"market": "Distillate — USGC ULSD", "product": "distillate", "cot": "gasoil",
         "keys": ["HO-WTI", "ULSD-WTI"], "region_name": "US Gulf", "margin_region": "US Gulf Coast"},
        {"market": "Distillate — Sing Gasoil", "product": "distillate", "cot": "gasoil",
         "keys": ["GO-Dubai"], "region_name": "Singapore", "margin_region": "Singapore"},
        {"market": "Gasoline — RBOB (US)", "product": "gasoline", "cot": "rbob",
         "keys": ["RBOB-Brent", "RBOB-WTI"], "region_name": "US Gulf", "margin_region": "US Gulf Coast"},
        {"market": "Gasoline — EBOB (Europe)", "product": "gasoline", "cot": "rbob",
         "keys": ["EBOB-Brt"], "region_name": "NW Europe", "margin_region": "North-West Europe"},
        {"market": "Jet — NWE", "product": "distillate", "cot": "gasoil",
         "keys": ["JetNWE-Brt"], "region_name": "NW Europe", "margin_region": "North-West Europe"},
    ]
    for cfg in crack_cfgs:
        sig, cc = _first_crack(ctx, curves, *cfg["keys"])
        if not sig:
            continue
        mgs = [m for m in ctx.get("margins", []) if m["region"] == cfg["margin_region"]]
        mg = max(mgs, key=lambda m: m["seasonal_pctile"] or 0) if mgs else None
        cot = ctx["cot"].get(cfg["cot"])
        r = _crack_recommendation(cfg, sig, cc, ctx["flat"].get("Brent"), cot, mg, news_products.get(cfg["product"]))
        if r:
            recs.append(r)
    return recs


def _news_hits(products):
    """One-line news catalyst per product (first relevant sentence), for corroboration."""
    out = {}
    for p in products:
        ex = news_excerpt(p, limit=1200)
        if not ex:
            continue
        # take the first sentence-ish fragment
        frag = ex.replace("\n", " ").strip()
        frag = frag[:180].rsplit(".", 1)[0].strip()
        if frag:
            out[p] = frag + "."
    return out


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
    "levels, w/w changes, percentiles, curve shape and positioning. Tone: sharp, non-hedging. "
    "If a MARKET NEWS section is provided, weigh it heavily in your analysis: reconcile the "
    "platform's computed signals with the news (geopolitics, outages, arbs, export bans), "
    "flag agreements/contradictions between the two, and fold the key news catalysts into the "
    "TL;DR and What to Watch. Attribute news facts as 'per latest market intel'."
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
        news = news_excerpt(product)
        user_msg = (f"Product: {product}. Region: {region}.\n"
                    f"Computed signals JSON:\n{_json.dumps(base, default=str)[:6000]}\n"
                    f"Broader context JSON:\n{_json.dumps(ctx, default=str)[:6000]}"
                    + (f"\n\nMARKET NEWS (latest analyst intel):\n{news}" if news else ""))
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
