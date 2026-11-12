"""Regenerate app/pricing_data.json from an uploaded prices workbook.

Layout per sheet: row1 = title, row2 = ticker headers every 3rd col,
row3 = 'Date'/label pairs, data from row4. Columns come in (Date, value, blank) triplets.
"""
import json, sys, datetime
import openpyxl

SRC = sys.argv[1]
OUT = "/home/ubuntu/crude-oil-analytics/app/pricing_data.json"
OLD = OUT

def clean_val(v):
    if v is None:
        return None
    if isinstance(v, datetime.datetime):
        return None  # bad cell (Excel date artifact)
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None

wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
groups = []
for ws in wb.worksheets:
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 4:
        continue
    title = str(rows[0][0] or ws.title).strip()
    tick_row, lab_row = rows[1], rows[2]
    ncols = len(lab_row)
    series = []
    for c in range(0, ncols, 3):
        if c + 1 >= ncols:
            break
        label = lab_row[c + 1]
        ticker = tick_row[c]
        if not label:
            continue
        ticker = str(ticker).replace(" Comdty", "").strip() if ticker else str(label)
        dates, values = [], []
        for r in rows[3:]:
            if c + 1 >= len(r):
                continue
            d, v = r[c], clean_val(r[c + 1])
            if not isinstance(d, datetime.datetime) or v is None:
                continue
            dates.append(d.strftime("%Y-%m-%d"))
            values.append(v)
        if dates:
            series.append({"label": str(label).strip(), "ticker": ticker,
                           "dates": dates, "values": values})
    if series:
        sheet = ws.title.strip()
        sheet = {"Dubai": "Dubai Crude", "Swaps EU": "Swaps Eur"}.get(sheet, sheet)
        groups.append({"sheet": sheet, "title": title, "series": series})

# Preserve groups from old file that are absent in the new workbook (e.g. Swaps Asia)
try:
    old = json.load(open(OLD))
    new_sheets = {g["sheet"].lower() for g in groups}
    for g in old.get("groups", []):
        key = g["sheet"].strip().lower()
        if key not in new_sheets:
            print("Preserving legacy group:", g["sheet"])
            groups.append(g)
except FileNotFoundError:
    pass

out = {"groups": groups, "generated": datetime.datetime.utcnow().isoformat()}
json.dump(out, open(OUT, "w"))
for g in groups:
    last = max(s["dates"][-1] for s in g["series"])
    print(g["sheet"], len(g["series"]), "series, last date", last)
