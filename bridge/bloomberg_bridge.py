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
    if wb_name in ("active", "", None):
        wb = xw.books.active
    else:
        # attach to an already-open book by name, else open it
        try:
            wb = xw.books[os.path.basename(wb_name)]
        except Exception:
            wb = xw.Book(wb_name)

    layout = cfg.get("layout", "row")
    sheets = cfg.get("sheets")  # None => all sheets
    header_row = int(cfg.get("header_row", 1))
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
            if len(vals) < header_row + 1:
                continue
            headers = vals[header_row - 1]
            # last row that has any numeric data = latest / live row
            last_row = None
            for row in reversed(vals[header_row:]):
                if any(_num(c) is not None for c in row):
                    last_row = row
                    break
            if last_row is None:
                continue
            for j, lab in enumerate(headers):
                if lab is None or str(lab).strip().lower() in skip:
                    continue
                if j >= len(last_row):
                    continue
                v = _num(last_row[j])
                if v is not None:
                    ticks[str(lab).strip()] = v
    return ticks


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
    state = {}

    print(f"[bridge] mode={mode}  platform={platform_url}  every {interval}s")
    print("[bridge] Keep the Bloomberg Terminal + workbook open. Ctrl+C to stop.\n")

    while True:
        t0 = time.time()
        try:
            ticks = read_excel(cfg) if mode == "excel" else read_blpapi(cfg, state)
        except Exception as e:  # noqa: BLE001
            print(f"[bridge] read error: {e}")
            ticks = {}

        if ticks:
            res = push(platform_url, token, ticks, cfg.get("source", "bloomberg-bridge"))
            if res.get("error"):
                print(f"[bridge] push error: {res['error']}")
            else:
                print(f"[bridge] pushed {res.get('updated', 0)} of {len(ticks)} "
                      f"@ {time.strftime('%H:%M:%S')}")
        else:
            print("[bridge] no numeric values read — check layout/sheets in config")

        if args.once:
            break
        time.sleep(max(0.5, interval - (time.time() - t0)))


if __name__ == "__main__":
    main()
