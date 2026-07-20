#!/usr/bin/env python3
"""
Barrel Terminal — Bloomberg live-price bridge.

Runs on the Windows PC where the Bloomberg Terminal is logged in and an Excel
workbook with live BDP/RTD price formulas is open. Reads the live cells every
few seconds and pushes them to the Barrel Terminal platform, which overlays them
on the Pricing and Cross-Market charts in real time.

Two data sources are supported (choose in bridge_config.json → "mode"):

  "excel"  (default, recommended) — reads the open Bloomberg Excel workbook via
           xlwings. No ticker mapping needed: it reuses whatever formulas already
           compute your prices/cracks/swaps. Keep the workbook open.

  "blpapi" — subscribes to real-time market data straight from the Terminal
           (no Excel). Requires the Bloomberg Desktop API (blpapi) and a
           label -> Bloomberg-security map in the config ("securities").

Nothing here needs the user's Bloomberg login: the Terminal's own session on the
machine provides entitlement, exactly like Excel's BDP functions.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "bridge_config.json")


def load_config(path):
    if not os.path.exists(path):
        sys.exit(
            f"Config not found: {path}\n"
            "Copy bridge_config.example.json to bridge_config.json and edit it."
        )
    with open(path) as f:
        return json.load(f)


def push(platform_url, token, ticks, source="bloomberg-bridge"):
    """POST the collected ticks to the platform's live-ingest endpoint."""
    url = platform_url.rstrip("/") + "/api/pricing/live"
    body = json.dumps({"ticks": ticks, "source": source}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Ingest-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:  # noqa: BLE001 - report and keep the loop alive
        return {"error": str(e)}


# ─────────────────────────── Excel (xlwings) source ────────────────────────
def _num(v):
    """Return v as a float if it's a real number, else None (skip dates/text)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        # Excel serial dates land in a huge range; treat obvious dates as non-price
        return f
    return None


def _detect_header_row(vals, max_scan=8):
    """Pick the row that holds the column labels. Prefers a row with many
    short text tokens (e.g. Date, CO1, CO2…) over a long descriptive title."""
    best_idx, best_score = 0, -1
    for i, row in enumerate(vals[:max_scan]):
        shortish = [c for c in row
                    if isinstance(c, str) and c.strip() and len(c.strip()) <= 16]
        score = len(shortish)
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx


def read_excel(cfg):
    """Read the open Bloomberg workbook and return {label: value}.

    Layouts (cfg["layout"]):
      "row"    — labels in a header row, latest values in the last data row
                 (matches an exports-style sheet: Date column + one column per
                 series with dates going down and today's live value at bottom).
      "column" — labels down one column, live value in an adjacent column
                 (a dashboard sheet: A=label/ticker, B=live price).
    """
    import xlwings as xw

    wb_name = cfg.get("workbook", "active")
    # Books that are NOT the prices workbook (positioning + volume/OI). When the
    # prices workbook is auto-selected ("active"), never read prices from these.
    other_bases = set()
    for key in ("positioning", "voloi"):
        w = ((cfg.get(key) or {}).get("workbook") or "")
        if w:
            other_bases.add(os.path.basename(w))
    if wb_name in ("active", "", None):
        wb = xw.books.active
        # If the focused book is one of the non-price books, read prices from a
        # different open book instead (so having them open doesn't clobber prices).
        if wb is not None and wb.name in other_bases:
            for b in xw.books:
                if b.name not in other_bases:
                    wb = b
                    break
    else:
        # attach to an already-open book by name, else open it
        try:
            wb = xw.books[os.path.basename(wb_name)]
        except Exception:
            wb = xw.Book(wb_name)

    layout = cfg.get("layout", "row")
    sheets = cfg.get("sheets")  # None => all sheets
    header_cfg = cfg.get("header_row", "auto")
    skip = {s.lower() for s in cfg.get("skip_labels", ["date", "dates", ""])}
    ticks = {}

    target_sheets = wb.sheets if not sheets else [wb.sheets[s] for s in sheets]
    for sht in target_sheets:
        used = sht.used_range
        vals = used.value
        if not vals or not isinstance(vals, list):
            continue
        # normalise to a 2D list
        if not isinstance(vals[0], list):
            vals = [vals]

        if layout == "column":
            lab_col = int(cfg.get("label_col", 1)) - 1
            val_col = int(cfg.get("value_col", 2)) - 1
            for row in vals:
                if len(row) <= max(lab_col, val_col):
                    continue
                lab = row[lab_col]
                if lab is None or str(lab).strip().lower() in skip:
                    continue
                v = _num(row[val_col])
                if v is not None:
                    ticks[str(lab).strip()] = v
        else:  # "row"
            auto_idx = _detect_header_row(vals)
            if header_cfg == "auto":
                hidx = auto_idx
            else:
                hidx = int(header_cfg) - 1
                # Self-correct a bad/stale header_row (e.g. pointing at a title
                # row): if it yields far fewer labels than auto-detection, use
                # auto instead so the bridge works without editing the config.
                def _nlabels(i):
                    if i < 0 or i >= len(vals):
                        return 0
                    return sum(1 for c in vals[i]
                               if isinstance(c, str) and c.strip()
                               and c.strip().lower() not in skip)
                if _nlabels(hidx) < _nlabels(auto_idx):
                    hidx = auto_idx
            if len(vals) < hidx + 2:
                continue
            headers = vals[hidx]
            data = vals[hidx + 1:]
            # Each series is its own column and columns can have different
            # history lengths (ragged), so take the LAST numeric value found in
            # each labelled column independently rather than one shared row.
            for j, lab in enumerate(headers):
                if lab is None or str(lab).strip().lower() in skip:
                    continue
                for row in reversed(data):
                    if j < len(row):
                        v = _num(row[j])
                        if v is not None:
                            ticks[str(lab).strip()] = v
                            break
    return ticks


def push_positioning(platform_url, token, data, source="bloomberg-bridge"):
    """POST the structured positioning grid to the platform."""
    url = platform_url.rstrip("/") + "/api/positioning/live"
    body = json.dumps({"data": data, "source": source}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Ingest-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# ─── Positioning grid (Sparta-style order-level sheet) parsing ──────────────
def _pstr(v):
    return str(v).strip() if v is not None else ""


def _pnum(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def parse_positioning(vals):
    """Parse a positioning sheet's 2D cell grid into a structured payload.

    The sheet lays out instrument blocks on a fixed 9-column template whose
    header row reads MSET | Strategy | Inst. | Level | Distance $ | Distance % |
    Est. Lots | New %LS | New Lots. Above each header: a title row, a
    %Position row (TREND / REVERSION / VALUE), a Net Lots row, and a
    Current Prices row (Last / High / Low). Blocks repeat horizontally
    (3 across) and vertically. Everything is located relative to each 'MSET'
    header cell, so extra columns/rows don't matter.
    """
    if not vals:
        return {"instruments": []}
    if not isinstance(vals[0], list):
        vals = [vals]
    nrows = len(vals)

    def get(r, c):
        if 0 <= r < nrows and 0 <= c < len(vals[r]):
            return vals[r][c]
        return None

    # locate all (header_row, mset_col) anchors
    anchors = []
    for r in range(nrows):
        row = vals[r]
        for c in range(len(row)):
            if _pstr(row[c]) == "MSET" and _pstr(get(r, c + 1)) == "Strategy":
                anchors.append((r, c))
    # reading order: top-to-bottom bands, left-to-right within a band
    anchors.sort(key=lambda a: (a[0], a[1]))

    instruments = []
    for hr, j in anchors:
        title = _pstr(get(hr - 4, j))
        fam = {
            "trend": {"pct": _pnum(get(hr - 3, j + 2)), "net_lots": _pnum(get(hr - 2, j + 2))},
            "reversion": {"pct": _pnum(get(hr - 3, j + 5)), "net_lots": _pnum(get(hr - 2, j + 5))},
            "value": {"pct": _pnum(get(hr - 3, j + 8)), "net_lots": _pnum(get(hr - 2, j + 8))},
        }
        last = _pnum(get(hr - 1, j + 4))
        high = _pnum(get(hr - 1, j + 6))
        low = _pnum(get(hr - 1, j + 8))
        rows = []
        settle = None
        r = hr + 1
        while r < nrows:
            cat = _pstr(get(r, j))
            strat = _pstr(get(r, j + 1))
            inst = _pstr(get(r, j + 2))
            if cat == "" and strat == "" and inst == "":
                break
            if cat == "MSET" or "% Position" in cat or (" - " in cat and "(" in cat):
                break
            if cat == "SETTLE":
                settle = _pnum(get(r, j + 3))
                r += 1
                continue
            rows.append({
                "mset": cat,
                "strategy": strat,
                "inst": inst,
                "level": _pnum(get(r, j + 3)),
                "dist_usd": _pnum(get(r, j + 4)),
                "dist_pct": _pnum(get(r, j + 5)),
                "est_lots": _pnum(get(r, j + 6)),
                "new_pct_ls": _pnum(get(r, j + 7)),
                "new_lots": _pnum(get(r, j + 8)),
                "alert": _pstr(get(r, j - 1)) if j >= 1 else "",
            })
            r += 1
        instruments.append({
            "title": title,
            "families": fam,
            "last": last, "high": high, "low": low, "settle": settle,
            "rows": rows,
        })
    return {"instruments": instruments}


def read_positioning_excel(cfg):
    """Read the positioning workbook (by name, so it can be open alongside the
    prices workbook) and return the structured grid for the configured sheet."""
    import xlwings as xw

    pcfg = cfg.get("positioning") or {}
    wb_name = pcfg.get("workbook", "")
    sheet = pcfg.get("sheet", "Energy")
    wb = None
    if wb_name in ("active", "", None):
        wb = xw.books.active
    else:
        base = os.path.basename(wb_name)
        for b in xw.books:
            if b.name == base or b.name == wb_name:
                wb = b
                break
        if wb is None:
            # try any open app/book across instances
            for app_ in xw.apps:
                for b in app_.books:
                    if b.name == base:
                        wb = b
                        break
                if wb:
                    break
        if wb is None:
            raise RuntimeError(f"positioning workbook not open: {base}")
    try:
        sht = wb.sheets[sheet]
    except Exception:
        raise RuntimeError(f"sheet '{sheet}' not found in {wb.name}")
    vals = sht.used_range.value
    return parse_positioning(vals)


def push_voloi(platform_url, token, data, source="bloomberg-bridge"):
    """POST the latest 3-min volume/price bars + daily OI to the platform."""
    url = platform_url.rstrip("/") + "/api/voloi/live"
    body = json.dumps({"data": data, "source": source}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Ingest-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# ─── Volume & OI workbook (3-min bars + daily OI) parsing ───────────────────
# Intraday sheets carry [timestamp, last_price, volume] from row 4; daily OI
# sheets carry two contracts side-by-side (cols 0-2 and 5-7), newest-first.
_VOLOI_INTRADAY = {
    "CO1": {"sheet": "CO1_3min", "commodity": "Brent", "label": "Brent CO1 (front)", "unit": "$/bbl"},
    "CO2": {"sheet": "CO2_3min", "commodity": "Brent", "label": "Brent CO2 (2nd)", "unit": "$/bbl"},
    "XB1": {"sheet": "XB1_3min", "commodity": "RBOB", "label": "RBOB XB1 (front)", "unit": "\u00a2/gal"},
    "XB2": {"sheet": "XB2_3min", "commodity": "RBOB", "label": "RBOB XB2 (2nd)", "unit": "\u00a2/gal"},
    "QS1": {"sheet": "QS1_3min", "commodity": "Gasoil", "label": "Gasoil QS1 (front)", "unit": "$/t"},
    "QS2": {"sheet": "QS2_3min", "commodity": "Gasoil", "label": "Gasoil QS2 (2nd)", "unit": "$/t"},
}
_VOLOI_OI = {
    "Brent": {"sheet": "Brent_Daily_OI", "unit": "$/bbl", "c1": "CO1", "c2": "CO2"},
    "RBOB": {"sheet": "RBOB_Daily_OI", "unit": "\u00a2/gal", "c1": "XB1", "c2": "XB2"},
    "Gasoil": {"sheet": "Gasoil_Daily_OI", "unit": "$/t", "c1": "QS1", "c2": "QS2"},
}


def _is_dt(v):
    import datetime as _dt
    return isinstance(v, (_dt.datetime, _dt.date))


def _coerce_dt(v):
    """Return a datetime from either a real datetime/date OR an Excel serial
    number. Some sheets hand xlwings the timestamp as a raw serial (float) rather
    than a date-typed value, which would otherwise be dropped and freeze the feed."""
    import datetime as _dt
    if isinstance(v, _dt.datetime):
        return v
    if isinstance(v, _dt.date):
        return _dt.datetime(v.year, v.month, v.day)
    # Excel 1900 date system: serial days since 1899-12-30. Bound the range so a
    # plain price (e.g. 88.3) is never mistaken for a date. 30000..80000 ~= 1982..2119.
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 30000 < v < 80000:
        return _dt.datetime(1899, 12, 30) + _dt.timedelta(days=float(v))
    return None


def _read_range_retry(sheet, addr, tries=3):
    """Read a fixed range, retrying transient Excel-busy COM errors. Reading a
    fixed range (not used_range) avoids UsedRange lag when RTD writes new rows."""
    last = None
    for _ in range(tries):
        try:
            return sheet.range(addr).value
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4)
    raise last


def _fmt_dt(v, with_time):
    return v.strftime("%Y-%m-%dT%H:%M" if with_time else "%Y-%m-%d")


def read_voloi_excel(cfg, tail=800):
    """Read the Volume/OI workbook (by name, open alongside the others) and
    return {intraday:{code:{...,t,p,v}}, oi:{commodity:{contracts:[...]}}}.
    Only the last `tail` intraday bars per contract are sent to keep pushes small."""
    import xlwings as xw

    vcfg = cfg.get("voloi") or {}
    wb_name = vcfg.get("workbook", "")
    wb = None
    base = os.path.basename(wb_name) if wb_name else ""
    if base:
        for app_ in xw.apps:
            for b in app_.books:
                if b.name == base or b.name == wb_name:
                    wb = b
                    break
            if wb:
                break
    if wb is None:
        raise RuntimeError(f"volume/OI workbook not open: {base or '(name missing)'}")

    names = {s.name for s in wb.sheets}
    intraday = {}
    for code, meta in _VOLOI_INTRADAY.items():
        if meta["sheet"] not in names:
            continue
        vals = _read_range_retry(wb.sheets[meta["sheet"]], "A1:C9000")
        if not isinstance(vals, list):
            continue
        t, p, v = [], [], []
        for r in vals[3:]:
            if not isinstance(r, list) or len(r) < 3:
                continue
            dt = _coerce_dt(r[0])
            if dt is None:
                continue
            if not isinstance(r[1], (int, float)) or isinstance(r[1], bool):
                continue
            if not isinstance(r[2], (int, float)) or isinstance(r[2], bool):
                continue
            t.append(_fmt_dt(dt, True))
            p.append(round(float(r[1]), 4))
            v.append(int(r[2]))
        if t:
            intraday[code] = {"commodity": meta["commodity"], "label": meta["label"],
                              "unit": meta["unit"], "t": t[-tail:], "p": p[-tail:], "v": v[-tail:]}

    oi = {}
    for comm, meta in _VOLOI_OI.items():
        if meta["sheet"] not in names:
            continue
        vals = _read_range_retry(wb.sheets[meta["sheet"]], "A1:H2000")
        if not isinstance(vals, list):
            continue
        contracts = []
        for bcol, ccode in ((0, meta["c1"]), (5, meta["c2"])):
            recs = []
            for r in vals[3:]:
                if not isinstance(r, list) or bcol >= len(r):
                    continue
                d = _coerce_dt(r[bcol])
                if d is None:
                    continue
                px = r[bcol + 1] if bcol + 1 < len(r) else None
                oiv = r[bcol + 2] if bcol + 2 < len(r) else None
                recs.append((d,
                             float(px) if isinstance(px, (int, float)) and not isinstance(px, bool) else None,
                             int(oiv) if isinstance(oiv, (int, float)) and not isinstance(oiv, bool) else None))
            recs.sort(key=lambda x: x[0])
            contracts.append({"code": ccode,
                              "dates": [_fmt_dt(d, False) for d, _, _ in recs],
                              "px": [px for _, px, _ in recs],
                              "oi": [o for _, _, o in recs]})
        oi[comm] = {"unit": meta["unit"], "contracts": contracts}

    return {"intraday": intraday, "oi": oi}


def diagnose_excel(cfg):
    """Print what xlwings can see: which Excel app/workbook is open, its sheet
    names, and a small top-left sample of each sheet. Helps match the config."""
    try:
        import xlwings as xw
    except Exception as e:  # noqa: BLE001
        print(f"[diag] xlwings not importable: {e}")
        return
    try:
        n_apps = len(xw.apps)
    except Exception as e:  # noqa: BLE001
        print(f"[diag] cannot reach Excel: {e}")
        return
    print(f"[diag] Excel instances open: {n_apps}")
    if n_apps == 0:
        print("[diag] No Excel is open. Open your Bloomberg workbook in Excel first.")
        return
    try:
        wb = xw.books.active
    except Exception as e:  # noqa: BLE001
        print(f"[diag] no active workbook: {e}")
        return
    print(f"[diag] active workbook: {wb.name}")
    print(f"[diag] sheets: {[s.name for s in wb.sheets]}")
    for sht in wb.sheets:
        try:
            vals = sht.used_range.value
        except Exception:
            continue
        if not vals:
            print(f"[diag]   '{sht.name}': (empty)")
            continue
        if not isinstance(vals, list):
            vals = [[vals]]
        elif not isinstance(vals[0], list):
            vals = [vals]
        rows = len(vals)
        cols = max(len(r) for r in vals)
        hidx = _detect_header_row(vals)
        labels = [str(c).strip() for c in vals[hidx]
                  if isinstance(c, str) and c.strip()][:12]
        print(f"[diag]   '{sht.name}': {rows}r x {cols}c | header row {hidx + 1} "
              f"labels: {labels}")


# ─────────────────────────── blpapi source ─────────────────────────────────
def read_blpapi(cfg, state):
    """Subscribe to real-time LAST_PRICE for the configured securities and
    return the latest {label: value}. Maintains a persistent session in
    `state` across polls."""
    import blpapi

    securities = cfg.get("securities", {})  # {label: "CO1 Comdty", ...}
    if not securities:
        sys.exit('blpapi mode needs a "securities" map in the config.')

    if "session" not in state:
        opts = blpapi.SessionOptions()
        opts.setServerHost(cfg.get("blp_host", "localhost"))
        opts.setServerPort(int(cfg.get("blp_port", 8194)))
        session = blpapi.Session(opts)
        if not session.start() or not session.openService("//blp/mktdata"):
            sys.exit("Could not connect to the Bloomberg Terminal (blpapi).")
        sub = blpapi.SubscriptionList()
        rev = {}
        for lab, sec in securities.items():
            cid = blpapi.CorrelationId(lab)
            sub.add(sec, "LAST_PRICE,BID,ASK", "", cid)
            rev[lab] = lab
        session.subscribe(sub)
        state["session"] = session
        state["last"] = {}

    session = state["session"]
    last = state["last"]
    # drain events that have arrived since the previous poll
    while True:
        ev = session.nextEvent(50)
        if ev.eventType() in (blpapi.Event.SUBSCRIPTION_DATA,):
            for msg in ev:
                lab = msg.correlationIds()[0].value()
                for fld in ("LAST_PRICE", "BID"):
                    if msg.hasElement(fld):
                        last[lab] = msg.getElementAsFloat(fld)
                        break
        if ev.eventType() == blpapi.Event.TIMEOUT:
            break
    return dict(last)


def main():
    ap = argparse.ArgumentParser(description="Barrel Terminal Bloomberg bridge")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--once", action="store_true", help="push once and exit (test)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    platform_url = cfg["platform_url"]
    token = cfg["ingest_token"]
    mode = cfg.get("mode", "excel")
    interval = float(cfg.get("poll_seconds", 5))
    pos_cfg = cfg.get("positioning") or {}
    pos_on = mode == "excel" and pos_cfg.get("enabled", bool(pos_cfg.get("workbook")))
    voloi_cfg = cfg.get("voloi") or {}
    voloi_on = mode == "excel" and voloi_cfg.get("enabled", bool(voloi_cfg.get("workbook")))
    voloi_every = int(voloi_cfg.get("every_n_cycles", 10))  # OI/vol change slowly
    state = {}

    print(f"[bridge] mode={mode}  platform={platform_url}  every {interval}s")
    if pos_on:
        print(f"[bridge] positioning: ON  workbook='{pos_cfg.get('workbook')}'  "
              f"sheet='{pos_cfg.get('sheet', 'Energy')}'")
    else:
        print("[bridge] positioning: OFF (add a \"positioning\" block to "
              "bridge_config.json to enable)")
    if voloi_on:
        print(f"[bridge] volume/OI: ON  workbook='{voloi_cfg.get('workbook')}'  "
              f"every {voloi_every} cycles")
    else:
        print("[bridge] volume/OI: OFF (add a \"voloi\" block to "
              "bridge_config.json to enable)")
    print("[bridge] Keep the Bloomberg Terminal + workbook open. Ctrl+C to stop.\n")

    if mode == "excel":
        diagnose_excel(cfg)
        print()

    while True:
        t0 = time.time()
        ticks = {}
        last_err = None
        # Excel is often busy recalculating live Bloomberg (RTD) cells exactly when
        # we read — that raises "Call was rejected by callee". Retry a few times.
        for attempt in range(4):
            try:
                ticks = read_excel(cfg) if mode == "excel" else read_blpapi(cfg, state)
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(0.4)
        if last_err is not None and not ticks:
            print(f"[bridge] read error: {last_err}")

        if ticks:
            res = push(platform_url, token, ticks, cfg.get("source", "bloomberg-bridge"))
            if res.get("error"):
                print(f"[bridge] push error: {res['error']}")
            else:
                print(f"[bridge] pushed {res.get('updated', 0)} of {len(ticks)} "
                      f"@ {time.strftime('%H:%M:%S')}")
        else:
            print("[bridge] no numeric values read — check layout/sheets in config")

        if pos_on:
            try:
                pdata = read_positioning_excel(cfg)
                ninst = len(pdata.get("instruments", []))
                if ninst:
                    pres = push_positioning(platform_url, token, pdata,
                                            cfg.get("source", "bloomberg-bridge"))
                    if pres.get("error"):
                        print(f"[bridge] positioning push error: {pres['error']}")
                    else:
                        print(f"[bridge] positioning pushed {ninst} instruments "
                              f"@ {time.strftime('%H:%M:%S')}")
                else:
                    print("[bridge] positioning: no instruments parsed — check sheet")
            except Exception as e:  # noqa: BLE001
                print(f"[bridge] positioning read error: {e}")

        if voloi_on and (state.get("cycle", 0) % voloi_every == 0):
            try:
                vdata = read_voloi_excel(cfg, int(voloi_cfg.get("tail_bars", 800)))
                nc = len(vdata.get("intraday", {}))
                if nc:
                    vres = push_voloi(platform_url, token, vdata,
                                      cfg.get("source", "bloomberg-bridge"))
                    if vres.get("error"):
                        print(f"[bridge] volume/OI push error: {vres['error']}")
                    else:
                        tails = " ".join(
                            f"{c}->{(s['t'][-1][11:] if s.get('t') else '--')}"
                            for c, s in vdata["intraday"].items())
                        print(f"[bridge] volume/OI pushed {nc} contracts ({tails}) "
                              f"@ {time.strftime('%H:%M:%S')}")
                else:
                    print("[bridge] volume/OI: no contracts parsed — check workbook")
            except Exception as e:  # noqa: BLE001
                print(f"[bridge] volume/OI read error: {e}")
        state["cycle"] = state.get("cycle", 0) + 1

        if args.once:
            break
        time.sleep(max(0.5, interval - (time.time() - t0)))


if __name__ == "__main__":
    main()
