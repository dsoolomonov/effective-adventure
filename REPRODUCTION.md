# Barrel Terminal — Full Reproduction Guide

This document is a complete, self-contained recipe for standing up **Barrel Terminal**
(the "Crude & Products Market Intelligence" platform) from scratch — the FastAPI
backend, the vanilla-JS frontend, every external API integration, the Fly.io
deployment, and the local Windows Bloomberg bridge that streams live prices,
positioning and volume/OI.

Give this file + the repository to any engineer (or AI) and they can fully rebuild
the running system. **Secret values are NOT in this file** — they live in a
separate `.env` (see [Secrets](#3-secrets--credentials)). A filled secrets file is
delivered privately alongside this guide.

---

## 1. Architecture at a glance

```
                        ┌──────────────────────────────────────────────┐
   Your Windows PC      │                 Fly.io (sjc)                  │
   ┌───────────────┐    │   app: crude-oil-analytics                    │
   │ Bloomberg      │   │   ┌────────────────────────────────────────┐ │
   │ Terminal+Excel │   │   │ FastAPI (app/main.py, uvicorn :8000)    │ │
   │               │    │   │  • 165 REST endpoints (/api/*)          │ │
   │ bloomberg_     │    │   │  • password gate (coa_session cookie)   │ │
   │ bridge.py  ────┼────┼──▶│  • live ingest (X-Ingest-Token)         │ │
   │ (xlwings)      │HTTPS│   │  • static frontend (static/index.html) │ │
   └───────────────┘    │   └────────────────────────────────────────┘ │
        reads 3 books   │            │ pulls from external APIs         │
        pushes:         │            ▼                                  │
        • prices        │   EIA · JODI · Platts/SPGCI · Genscape ·      │
        • positioning   │   IIR · Kpler · Azure SQL · OpenAI            │
        • volume/OI     └──────────────────────────────────────────────┘
```

- **Backend:** FastAPI (`app/main.py`, ~13k lines, 165 routes) + `app/market_intel.py`.
- **Frontend:** single-page vanilla JS (`static/index.html` + `static/assets/*.js`), Plotly 2.27 charts.
- **Data snapshots:** committed JSON/XLSX in `app/` (margins, crude balances, COT, voloi, etc.) act as offline fallbacks so the platform renders even when live feeds/APIs are down.
- **Live feeds:** pushed from your PC by the bridge (Bloomberg is entitled to the local Terminal only — it can't run on the server).
- **Deploy:** Docker image → Fly.io, secrets stored as Fly secrets.

---

## 2. Repository layout

```
crude-oil-analytics/
├── Dockerfile              # python:3.12-slim + msodbcsql18 (Azure SQL driver)
├── fly.toml                # Fly app config (app=crude-oil-analytics, port 8000)
├── pyproject.toml          # Python deps (installed via `pip install .`)
├── app/
│   ├── main.py             # FastAPI app: all endpoints, auth, ingest, loaders
│   ├── market_intel.py     # market-commentary / LLM helpers, curve builders
│   ├── *.json / *.xlsx     # committed data snapshots (offline fallbacks)
│   └── market_news.txt
├── static/
│   ├── index.html          # SPA shell + nav
│   └── assets/…            # money-positioning.js (Money Pos + Volume/OI), etc.
├── bridge/                 # runs on YOUR Windows PC (not deployed)
│   ├── bloomberg_bridge.py # xlwings reader → pushes prices/positioning/voloi
│   ├── bridge_config.example.json
│   ├── run_bridge.bat      # one-click launcher (installs deps, runs bridge)
│   └── requirements.txt
└── db/                     # optional Azure SQL sync (Kpler → SQL)
    ├── connection.py, kpler_sync.py, migrate.py, refresh.py
    └── schema.sql, kpler_schema.sql
```

---

## 3. Secrets & credentials

All credentials are read from environment variables (with a `.env` file loaded at
startup — see `app/main.py:18-27`). On Fly they are stored as **Fly secrets**.

Copy `.env.example` → `.env` and fill every value (the private secrets file
shipped with this guide already has them filled). Then either run locally with
`.env`, or push them to Fly with the command in [§6](#6-deploy-to-flyio).

| Env var | Used for | Where to get it |
|---|---|---|
| `APP_PASSWORD` | Browser login gate (shared password). Also derives the auth-cookie signing key and the default ingest token. | You choose it. |
| `LIVE_INGEST_TOKEN` | Auth for the local bridge → `/api/*/live` ingest (`X-Ingest-Token`). | You choose a random 32-char string; must match `bridge_config.json`. |
| `EIA_API_KEY` | US EIA petroleum data (SND, stocks, imports/exports). Has a working default hard-coded in `main.py`. | https://www.eia.gov/opendata/register.php |
| `SPGCI_USERNAME` / `SPGCI_PASSWORD` | Platts / S&P Global (SPGCI) API (`api.platts.com`). | S&P Global Platts account. *(Same login as Kpler in this deployment.)* |
| `KPLER_USERNAME` / `KPLER_PASSWORD` | Kpler SDK (flows, inventories, refinery data). | Kpler account. |
| `GSPE_API_KEY` | Genscape / Wood Mackenzie storage & pipeline (`api.genscape.com`) — US/Cushing. | Genscape account. |
| `GSPE_EU_API_KEY` | Genscape Europe dataset. | Genscape account. |
| `IIR_USERNAME` / `IIR_PASSWORD` | IIR / Industrial Info refinery turnarounds (`api.industrialinfo.com`). Has defaults in `main.py`. | IIR account. |
| `AZURE_SQL_SERVER` / `AZURE_SQL_DATABASE` / `AZURE_SQL_USERNAME` / `AZURE_SQL_PASSWORD` | Optional Azure SQL store for Kpler sync. | Your Azure SQL instance. |
| `USE_AZURE_SQL` | `1` to enable the Azure SQL path, else `0`/unset. | — |
| `OPENAI_API_KEY` | Optional LLM market commentary / COT AI insight. | https://platform.openai.com/api-keys |
| `ANTHROPIC_API_KEY` | Optional alternative LLM (Claude). | https://console.anthropic.com |
| `MARKET_LLM_MODEL` / `MARKET_LLM_MODEL_ANTHROPIC` | Optional model overrides (defaults `gpt-4o-mini` / `claude-3-5-sonnet`). | — |

> Security note: never commit `.env` or the filled secrets file to git — it is
> already covered by `.gitignore`. Rotate `LIVE_INGEST_TOKEN`, `APP_PASSWORD` and
> any API keys if this bundle is shared beyond trusted hands.

---

## 4. External API integrations

| Source | Base URL | Auth | Endpoints that use it |
|---|---|---|---|
| **EIA** (US gov petroleum) | `https://api.eia.gov/v2` | `api_key` query param | `/api/eia*`, `/api/eia_sd/*`, `/api/eia_gasoline_*` |
| **JODI** (world oil data) | `https://www.jodidata.org/.../world_secondary_csv.zip` | none (public zip) | `/api/jodi_gasoline`, `/api/jodi_refresh` |
| **Platts / SPGCI** | `https://api.platts.com` | OAuth user/pass → bearer | Platts benchmarks/curves/news endpoints |
| **Genscape** | `https://api.genscape.com` | `GSPE_API_KEY` header | `/api/genscape/*` |
| **IIR** | `https://api.industrialinfo.com/idb/v2.4` | user/pass | `/api/iir/*` |
| **Kpler** | `kpler_sdk` (PyPI) | user/pass | `/api/kpler/*` |
| **Azure SQL** | `*.database.windows.net` | user/pass (ODBC 18) | `/api/db/*`, Kpler→SQL sync |
| **OpenAI / Anthropic** | api.openai.com / api.anthropic.com | bearer key | `/api/cot/ai-insight`, market commentary |

All external calls are **server-side** — no third-party credentials ever reach the
browser. When an API key is missing the corresponding tab degrades gracefully to
the committed snapshot data.

### Live ingest endpoints (fed by the bridge, not external APIs)
- `POST /api/live` — prices (bulk `{label: value}` map)
- `POST /api/positioning/live` — order-level positioning (FinFlows Energy sheet)
- `POST /api/voloi/live` — 3-min volume + daily OI (6 contracts)
- `GET /api/voloi`, `GET /api/voloi/live`, `GET /api/positioning/live` — read-side

All three POSTs require header `X-Ingest-Token: <LIVE_INGEST_TOKEN>`.

---

## 5. Run locally

```bash
git clone <this repo>
cd crude-oil-analytics
python3.12 -m venv .venv && . .venv/bin/activate
pip install .                      # reads pyproject.toml
cp .env.example .env               # then fill in secret values
uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://127.0.0.1:8000  → log in with APP_PASSWORD
```

Notes:
- `pyodbc` needs the Microsoft ODBC Driver 18 for SQL Server if `USE_AZURE_SQL=1`
  (the Dockerfile installs `msodbcsql18`; locally install it or leave Azure SQL off).
- Without any secrets the app still boots and serves the committed snapshots; live
  tabs simply show the offline baseline until the bridge/APIs are wired.

---

## 6. Deploy to Fly.io

One-time:
```bash
curl -L https://fly.io/install.sh | sh      # installs flyctl
flyctl auth login
flyctl apps create crude-oil-analytics       # or `flyctl launch` to generate fly.toml
```

Push every secret (run once; values from your `.env`):
```bash
flyctl secrets set -a crude-oil-analytics \
  APP_PASSWORD='…' \
  LIVE_INGEST_TOKEN='…' \
  SPGCI_USERNAME='…' SPGCI_PASSWORD='…' \
  KPLER_USERNAME='…' KPLER_PASSWORD='…' \
  GSPE_API_KEY='…' GSPE_EU_API_KEY='…' \
  IIR_USERNAME='…' IIR_PASSWORD='…' \
  AZURE_SQL_SERVER='…' AZURE_SQL_DATABASE='…' \
  AZURE_SQL_USERNAME='…' AZURE_SQL_PASSWORD='…' USE_AZURE_SQL='1' \
  OPENAI_API_KEY='…'
```

Deploy:
```bash
flyctl deploy --now              # builds Dockerfile, rolling-updates machines
```
App serves at `https://<app-name>.fly.dev/`. `fly.toml` pins internal port 8000,
1 GB RAM, min 1 machine running. (A harmless `not listening on expected address`
warning can appear during rollout; health checks still pass.)

To read the currently-deployed secret *values* back (they're injected as env vars):
```bash
flyctl ssh console -a crude-oil-analytics -C "/bin/sh -c 'env | sort'"
```

---

## 7. The Bloomberg bridge (local Windows PC)

The bridge streams live data from Bloomberg into the platform. It must run on the
PC logged into the Bloomberg Terminal (Bloomberg entitlement is local-only).

**Keep three workbooks open in Excel** while the bridge runs:
1. Your **live prices** workbook (Bloomberg RTD/BDP formulas).
2. `FinFlows_Stacked_Order_Levels_Bloomberg.xlsx` (positioning; `Energy` sheet).
3. `Energy_Volume_OI_Tracker.xlsx` (3-min volume + daily OI; 9 sheets).

Setup:
1. Install Python 3 (tick *Add to PATH*).
2. Put the `bridge/` folder somewhere **outside OneDrive** (e.g. `C:\barrel-bridge`)
   to avoid OneDrive reparse-path issues with Anaconda.
3. Copy `bridge_config.example.json` → `bridge_config.json` and set:
   - `platform_url`: `https://<app-name>.fly.dev`
   - `ingest_token`: the exact `LIVE_INGEST_TOKEN` value.
   - keep the `positioning` and `voloi` blocks (see example) so the price
     auto-selector excludes those two workbooks.
4. Double-click **`run_bridge.bat`** (installs deps first run). Ensure the launcher
   points at `bloomberg_bridge.py` (a doubled `.py.py` name is a common typo).

Healthy output every cycle:
```
[bridge] pushed 169 of 169 @ HH:MM:SS
[bridge] positioning pushed 8 instruments @ HH:MM:SS
[bridge] volume/OI pushed 6 contracts (CO1->… CO2->…) @ HH:MM:SS   # every ~10 cycles
```
The transient `read error: (-2147418111, 'Call was rejected by callee')` is
harmless — Excel was mid-recalc; the bridge retries and recovers next cycle.

`bridge_config.json` shape:
```json
{
  "platform_url": "https://crude-oil-analytics.fly.dev",
  "ingest_token": "<LIVE_INGEST_TOKEN>",
  "mode": "excel",
  "poll_seconds": 5,
  "source": "bloomberg-bridge",
  "workbook": "active",
  "layout": "row",
  "sheets": null,
  "header_row": "auto",
  "skip_labels": ["date", "dates", ""],
  "label_col": 1, "value_col": 2,
  "positioning": { "enabled": true, "workbook": "FinFlows_Stacked_Order_Levels_Bloomberg.xlsx", "sheet": "Energy" },
  "voloi":       { "enabled": true, "workbook": "Energy_Volume_OI_Tracker.xlsx", "every_n_cycles": 10, "tail_bars": 800 }
}
```

---

## 8. Refreshing data snapshots

The committed `app/*.json` snapshots are regenerated from source workbooks with the
`convert_*.py` scripts (kept outside the repo, in the operator's home dir). Typical
flow: drop a new workbook, point the script's `SRC` at it, run it, commit the JSON,
`flyctl deploy`. Examples:
- `convert_margins.py` → `app/margins_data.json` (FGE/NexantECA "Weekly Margins" sheet)
- `convert_voloi.py` → `app/voloi.json` (Energy_Volume_OI_Tracker.xlsx, 9 sheets)
- `convert_crude_bal_v2.py`, `convert_local_balances.py`, `convert_product_stocks.py`, etc.
- COT: replace `app/cot_latest.xlsx` (sheets WTI/Brent/Gasoil/RBOB) and redeploy.

---

## 9. Endpoint inventory (165 routes)

Grouped by tab/domain (full list: `grep -E '^@app\.(get|post|put|delete)' app/main.py`):
- **Positioning/Pricing:** `/api/cot/*`, `/api/cot_multi/*`, `/api/positioning/live`, `/api/co_prices`, `/api/live`
- **Volume & OI:** `/api/voloi`, `/api/voloi/live`
- **Margins:** `/api/margins`, `/api/ea_margins/*`, `/api/fge*`
- **Balances/Stocks:** `/api/cb/*` (crude balances), `/api/balances/*`, `/api/lem/*`, `/api/eia_gasoline_*`, `/api/jodi_gasoline`, `/api/jodi_refresh`
- **Refineries:** `/api/genscape/*`, `/api/iir/*`
- **Kpler:** `/api/kpler/*`
- **DB/admin:** `/api/db/*`
- **Backtesting/analytics:** `/api/backtest*`, `/api/instruments/*`, `/api/datasets/*`, `/api/combinations/*`

---

## 10. Quick reproduction checklist

1. `git clone` the repo.
2. `cp .env.example .env` and fill secrets (or use the shipped filled `.env`).
3. Local smoke test: `pip install . && uvicorn app.main:app --port 8000` → log in.
4. `flyctl launch`/`apps create`, `flyctl secrets set …`, `flyctl deploy --now`.
5. On the Bloomberg PC: configure `bridge_config.json` (token + `platform_url`),
   open the 3 workbooks, run `run_bridge.bat`.
6. Verify green **● LIVE** badge on Pricing / Volume & OI / Money Positioning tabs.
