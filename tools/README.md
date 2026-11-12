# tools/ — scripts used to build and check the platform

These scripts are the operator-side code that turned source files (Excel packs, PDFs,
API pulls) into the `app/*.json` snapshots, plus the browser checks used after each
deploy. They are **not** used by the running app. Most read inputs from the
operator's home directory (`/home/ubuntu/...`) — change the `SRC`/path constants
at the top of each script before running it.

| Folder / file | What it does | Output |
|---|---|---|
| `convert_margins.py` | FGE/NexantECA "Weekly Margins" workbook → JSON | `app/margins_data.json` |
| `convert_voloi.py` | `Energy_Volume_OI_Tracker.xlsx` (9 sheets) → JSON | `app/voloi.json` |
| `convert_crude_balances.py`, `convert_crude_bal_v2.py` | crude balance workbooks → JSON | `app/crude_balances_data.json`, `app/crude_bal_v2.json` |
| `convert_local_balances.py`, `convert_lem_quarterly*.py`, `extract_lem.py` | local/LEM balance workbooks → JSON | `app/local_balances.json`, `app/lem_quarterly.json` |
| `convert_asia_balances.py` | Asia balance pack → JSON | `app/asia_balances.json` (private) |
| `convert_pricing.py` | pricing workbook → JSON | `app/pricing_data.json` |
| `convert_product_stocks.py` | static Product Stocks fallback | `app/product_stocks.json` |
| `outages/`, `outg/` | refinery-outage PDF pack → JSON + chart images | `app/outages.json`, `app/outages_pack/` (private) |
| `arbs/` | EA crude arb tables → JSON; FGE vs Platts cross-check | `app/crude_arbs.json` |
| `cdx/`, `pstk/` | Platts symbol probes for Crude Differentials / Product Stocks | — |
| `bfoe/` | Platts BFOE strip / assessment checks | — |
| `xmove/` | Cross-Asset Moves: Bloomberg intraday + Platts daily pulls | `app/cross_moves_intraday.json` (private) |
| `sessprice/` | Session Pricing build from the user workbook | `app/session_pricing.json` (private) |
| `sig/` | Signal Azure SQL queries: Hormuz, dark transits, Yanbu, PADD1 | ad-hoc analysis |
| `eia_wk/`, `runs_bal/`, `jodi_*/` | EIA weekly / PSM, refinery runs, JODI analyses | ad-hoc analysis |
| `ea/` | Energy Aspects dataset mapping | `app/ea_config.json` |
| `*/ui.py`, `*/shot*.py` | Playwright checks via Chrome CDP (`localhost:29229`): open a tab, wait for charts, screenshot, print page errors | screenshots |
| `make_private_bundle.sh` | zips the git-ignored data files for private hand-over | `barrel-terminal-private-data.zip` |

Credentials always come from environment variables (see `../.env.example`); no
script contains a key or password.
