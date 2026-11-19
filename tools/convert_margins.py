"""Refresh weekly refinery margins JSON from the Weekly Margins sheet."""
import json
import openpyxl

SRC = "/home/ubuntu/attachments/18bf1c0a-bb08-4b1f-9b8b-40e4d9f02011/FGE+NexantECA+-+Products++Refining+in+Focus+-+Datafile+-+20+July+2026.xlsx"

# col index (0-based) -> (key, region, name)
COLS = [
    (2, "nwe_hydro", "North-West Europe", "Brent Hydroskimming"),
    (3, "nwe_fcc", "North-West Europe", "Brent FCC"),
    (5, "med_hydro", "Mediterranean", "Brent Hydroskimming"),
    (6, "med_fcc", "Mediterranean", "Brent FCC"),
    (8, "usgc_lls_fcc", "US Gulf Coast", "LLS FCC"),
    (9, "usgc_mars_cok", "US Gulf Coast", "Mars Coking"),
    (11, "sgp_hydro", "Singapore", "Dubai Hydroskimming"),
    (12, "sgp_fcc", "Singapore", "Dubai FCC"),
    (13, "sgp_hdc", "Singapore", "Dubai HDC"),
    (14, "sgp_rfcc", "Singapore", "Dubai RFCC"),
]

wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
ws = wb["Weekly Margins"]

dates = []
vals = {c[1]: [] for c in COLS}
for row in ws.iter_rows(min_row=3, max_row=ws.max_row, values_only=True):
    d = row[0]
    if not hasattr(d, "strftime"):
        continue
    dates.append(d.strftime("%Y-%m-%d"))
    for idx, key, _, _ in COLS:
        v = row[idx] if idx < len(row) else None
        vals[key].append(round(float(v), 4) if isinstance(v, (int, float)) else None)

margins = [{"key": key, "region": reg, "name": name, "values": vals[key]}
           for _, key, reg, name in COLS]

out = {"dates": dates, "margins": margins}
with open("/home/ubuntu/crude-oil-analytics/app/margins_data.json", "w") as f:
    json.dump(out, f)

print("weeks", len(dates), dates[0], "->", dates[-1])
for m in margins:
    print(m["key"], "last", m["values"][-1])
