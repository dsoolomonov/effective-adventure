#!/usr/bin/env bash
# Zip the git-ignored data files (licensed / internal / hand-typed snapshots) so they
# can be handed over privately. Unzip at the repo root to restore them.
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-barrel-terminal-private-data.zip}"
files=(app/asia_balances.json app/brent_chains.json app/cross_moves_intraday.json
       app/dated_workbook.xlsx app/outages.json app/outages_pack
       app/product_stocks_note.json app/session_pricing.json)
present=(); for f in "${files[@]}"; do [ -e "$f" ] && present+=("$f") || echo "missing: $f"; done
rm -f "$out"; zip -qr "$out" "${present[@]}"
echo "wrote $out ($(du -h "$out" | cut -f1))"
