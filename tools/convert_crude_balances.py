"""Parse the extended global oil balance workbook (+ regional runs) into a
compact JSON file for the Crude Balances dashboard. Source branding is not
carried into the output."""
import json
import openpyxl

EXT = "/home/ubuntu/attachments/ac829cfa-cc04-428d-887e-88d5f1957705/FGE+Monthly+Extended+Global+Oil+Balance+Tables+July+2026.xlsm"
RUNS = "/home/ubuntu/attachments/f2b350af-a4a3-408e-bd3e-5896f3583a9e/d3f032259f488ac33c35c9556c1f5354803605b8ddc215180303c85d4d6.xlsx"

REGIONS = ["North America", "Latin America", "Europe", "FSU", "North Africa",
           "Africa", "Middle East", "Asia"]


def r1(x):
    return None if x is None else round(float(x), 1)


def month_cols(ws, header_row):
    row = list(ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True))[0]
    cols = [(i, c) for i, c in enumerate(row) if hasattr(c, "strftime")]
    months = [c.strftime("%Y-%m") for _, c in cols]
    idxs = [i for i, _ in cols]
    return months, idxs


def row_by_label(ws, label, first_row=1, last_row=None):
    last_row = last_row or ws.max_row
    for row in ws.iter_rows(min_row=first_row, max_row=last_row, values_only=True):
        if row and row[0] == label:
            return row
    return None


def series(ws, label, idxs, first_row=1, last_row=None):
    row = row_by_label(ws, label, first_row, last_row)
    if row is None:
        return None
    return [r1(row[i]) if i < len(row) else None for i in idxs]


wb = openpyxl.load_workbook(EXT, data_only=True, read_only=True)

# ── Crude Balance sheet ──
cb = wb["Crude Balance"]
months, idxs = month_cols(cb, 3)

supply = {reg: series(cb, reg, idxs, 5, 13) for reg in REGIONS}
demand = {reg: series(cb, reg, idxs, 16, 24) for reg in REGIONS}
balance = {reg: series(cb, reg, idxs, 41, 49) for reg in REGIONS}
glob = {
    "supply": series(cb, "Global", idxs, 5, 13),
    "demand": series(cb, "Global", idxs, 16, 24),
    "balance": series(cb, "Global", idxs, 41, 49),
    "refinery_intake": series(cb, "Global Refinery Intake", idxs, 26, 26),
}
quality = {
    "Biofuels": series(cb, "Biofuels", idxs),
    "NGLs": series(cb, "NGLs", idxs),
    "Condensate": series(cb, "Condensate (45 < API)", idxs),
    "Light": series(cb, "Light Crude (35 < API < = 45)", idxs),
    "Medium": series(cb, "Medium Crude (26 < API < = 35)", idxs),
    "Heavy": series(cb, "Heavy Crude (API < = 26)", idxs),
}

# ── FGEBalance summary sheet ──
fb = wb["FGEBalance"]
fmonths, fidxs = month_cols(fb, 5)
sd_summary = {
    "OECD Demand": series(fb, "OECD Demand", fidxs),
    "Non-OECD Demand": series(fb, "Non-OECD Demand (Apparent)", fidxs),
    "Total Demand": series(fb, "Total Demand (Apparent)", fidxs),
    "Total Supply": series(fb, "Total Supply", fidxs),
    "Call on OPEC+ crude": series(fb, "Call on OPEC+ crude", fidxs),
    "Call on OPEC crude": series(fb, "Call on OPEC crude", fidxs),
}
stock_change = {
    "Total Primary Stock Change": series(fb, "Total Primary Stock Change", fidxs, 16, 27),
    "Onland OECD Company Stocks Change": series(fb, "Onland OECD Company Stocks Change", fidxs, 16, 27),
    "Strategic Stocks": series(fb, "Strategic Stocks", fidxs, 16, 27),
}
stocks_mmb = {
    "Onland OECD Company Stocks": series(fb, "Onland OECD Company Stocks", fidxs, 29, 43),
    "OECD stocks Days Cover": None,
    "5 Year Average": series(fb, "Onland OECD Company Stocks 5 Year Average", fidxs, 29, 43),
}
# Days cover lives in col B ('OECD stocks Days Cover') label
for row in fb.iter_rows(min_row=29, max_row=43, values_only=True):
    if row and row[1] == "OECD stocks Days Cover":
        stocks_mmb["OECD stocks Days Cover"] = [r1(row[i]) if i < len(row) else None for i in fidxs]
        break
prices = {
    "Dated Brent": series(fb, "Dated Brent", fidxs, 44, 48),
    "WTI Cushing": series(fb, "WTI Cushing", fidxs, 44, 48),
    "Dubai M1": series(fb, "Dubai M1", fidxs, 44, 48),
    "Urals CIF NWE": series(fb, "Urals CIF NWE", fidxs, 44, 48),
}

# ── OPEC+ Output sheet ──
op = wb["OPEC+ Output"]
omonths, oidxs = month_cols(op, 2)
if not oidxs:
    # header may sit elsewhere; scan first 4 rows
    for hr in range(1, 5):
        omonths, oidxs = month_cols(op, hr)
        if oidxs:
            break
opec = {}
for label in ["Total OPEC OPEC+", "Total Non-OPEC OPEC+", "Total OPEC+",
              "Saudi Arabia", "Iraq", "Russia", "Kazakhstan",
              "Spare Capacity", "Effective Spare Capacity**"]:
    s = series(op, label, oidxs)
    if s:
        opec[label.replace("**", "")] = s

# ── Regional refinery runs (second/first workbook) ──
wb2 = openpyxl.load_workbook(RUNS, data_only=True, read_only=True)
gr = wb2["Global Runs"]
gmonths, gidxs = month_cols(gr, 2)
run_regions = ["Africa", "Asia Pacific", "China", "Rest of Asia", "Europe",
               "FSU", "Latin America", "Middle East", "North America", "Total"]
runs = {}
runs_yoy = {}
for reg in run_regions:
    # levels block (rows 3-12), yoy block (rows 15-24)
    lvl = series(gr, reg, gidxs, 3, 12) or series(gr, reg.strip(), gidxs, 3, 12)
    yoy = series(gr, reg, gidxs, 15, 24) or series(gr, reg.strip(), gidxs, 15, 24)
    # Global Runs labels sit in column B (index 1), not A -> use custom lookup
    if lvl is None:
        for row in gr.iter_rows(min_row=3, max_row=12, values_only=True):
            if row and (row[1] == reg or (isinstance(row[1], str) and row[1].strip() == reg)):
                lvl = [r1(row[i]) for i in gidxs]
                break
    if yoy is None:
        for row in gr.iter_rows(min_row=15, max_row=24, values_only=True):
            if row and (row[1] == reg or (isinstance(row[1], str) and row[1].strip() == reg)):
                yoy = [r1(row[i]) for i in gidxs]
                break
    if lvl:
        runs[reg] = lvl
    if yoy:
        runs_yoy[reg] = yoy

out = {
    "months": months,
    "current_month": "2026-06",
    "forecast_from": "2026-07",
    "regions": REGIONS,
    "supply": supply,
    "demand": demand,
    "balance": balance,
    "global": glob,
    "quality": quality,
    "sd_summary": sd_summary,
    "sd_months": fmonths,
    "stock_change": stock_change,
    "stocks_mmb": stocks_mmb,
    "prices": prices,
    "opec": opec,
    "opec_months": omonths,
    "runs_months": gmonths,
    "runs": runs,
    "runs_yoy": runs_yoy,
}

with open("/home/ubuntu/crude-oil-analytics/app/crude_balances_data.json", "w") as f:
    json.dump(out, f)

print("months", len(months), months[0], months[-1])
print("sd_months", len(fmonths), fmonths[0] if fmonths else None, fmonths[-1] if fmonths else None)
print("opec_months", len(omonths))
print("opec keys", list(opec.keys()))
print("runs_months", len(gmonths), gmonths[0] if gmonths else None, gmonths[-1] if gmonths else None)
print("runs regions", list(runs.keys()))
print("supply NA sample", supply["North America"][:3], "...", supply["North America"][-3:])
print("global refinery_intake last", glob["refinery_intake"][-3:])
print("prices Dated Brent last", prices["Dated Brent"][-3:])
