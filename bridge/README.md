# Barrel Terminal — Bloomberg live-price bridge

Streams live Bloomberg prices from your PC into the Barrel Terminal platform so
the **Pricing** and **Cross-Market** tabs update in real time (like Bloomberg
Excel). The prices refresh on *your* machine; this bridge reads them and pushes
them to the platform every few seconds.

## Why it runs on your machine

Bloomberg data is entitled to the Terminal session logged in on your PC (the same
thing that makes `=BDP(...)` work in Excel). It cannot run on a remote server, and
you should never share your Bloomberg login. So the bridge runs locally and only
sends the resulting numbers to the platform over an authenticated endpoint.

## Setup (Windows, one-click)

1. Install **Python 3** from https://python.org (tick *Add python.exe to PATH*).
2. In this `bridge` folder, copy `bridge_config.example.json` → `bridge_config.json`.
3. Paste your **ingest token** into `bridge_config.json` (ask the platform owner;
   it's the `LIVE_INGEST_TOKEN`).
4. Open the Bloomberg Terminal and your **live price workbook** in Excel.
5. Double-click **`run_bridge.bat`**. It installs dependencies on first run and
   starts streaming. Leave the window open.

You should see lines like `pushed 140 of 140 @ 14:03:21`, and the platform's
Pricing/Cross-Market tabs will show a green **● LIVE** badge.

## Excel mode (default)

Reuses your existing Bloomberg Excel formulas — no ticker mapping.

- `"layout": "row"` — one sheet per book (Brent, WTI, Gasoil…), a header row of
  series labels (`CO1`, `CO2`…), dates going down, and today's live value in the
  bottom row. Matches the `updatedprices.xlsx` export layout.
- `"layout": "column"` — a single dashboard sheet with labels/tickers down
  column A and the live price in column B (set `label_col` / `value_col`).
- `"sheets": null` reads every sheet; set e.g. `["Brent","WTI","Cracks"]` to limit.
- Labels must match the platform's series labels (`CO1`, `HO-WTI 1`, `EBOB M1`…).
  Anything that doesn't match is simply ignored.

Test without looping: `python bloomberg_bridge.py --once`

## blpapi mode (optional, no Excel)

Set `"mode": "blpapi"` and fill `"securities"` with `label → "TICKER Comdty"`.
Install the Bloomberg Python API:

```
pip install --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple blpapi
```

Cracks/spreads that don't have a single Bloomberg ticker are best handled in
Excel mode.
