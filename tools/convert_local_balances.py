"""Convert the Energy Aspects gasoline workbooks into app/local_balances.json.

Inputs (latest EA release, 2026-07-06):
  - global-gasoline-balances : monthly regional demand & supply (2010 -> 2027)
  - global-gasoline-supply   : monthly per-country supply by region sheet
  - global-gasoline-demand   : monthly per-country demand by region sheet
  - us-weekly-product-stock-forecast : weekly US + PADD gasoline balance
"""
import glob
import json
import re

import openpyxl

OUT = "/home/ubuntu/crude-oil-analytics/app/local_balances.json"
ATT = "/home/ubuntu/attachments/*/"
REGION_NAMES = {
    "WORLD": "World", "NA": "North America", "EUR": "Europe",
    "AP": "Asia Pacific", "LATAM": "Latin America", "ME": "Middle East",
    "FSU": "FSU", "AFR": "Africa",
}
START = "2015-01-01"


def find(pat):
    hits = sorted(glob.glob(ATT + pat))
    if not hits:
        raise SystemExit(f"missing attachment: {pat}")
    return hits[-1]


def rows_of(ws):
    return [list(r) for r in ws.iter_rows(values_only=True)]


def build_regions():
    wb = openpyxl.load_workbook(find("energyaspects_global-gasoline-balances_*.xlsx"), read_only=True)
    rows = rows_of(wb["Data"])
    hdr = rows[0]
    meta = {r[0]: r[1:] for r in rows_of(wb["Metadata"])}
    region_row = ["Date"] + list(meta["region"])
    aspect_row = ["date"] + list(meta["aspect"])
    fstart_row = ["d"] + list(meta["forecast_start_date"])
    out = {}
    dates = [str(r[0])[:10] for r in rows[1:]]
    keep = [i for i, d in enumerate(dates) if d >= START]
    for code, name in REGION_NAMES.items():
        entry = {"name": name, "dates": [dates[i] for i in keep]}
        for j in range(1, len(hdr)):
            if region_row[j] == code:
                col = [rows[1 + i][j] for i in keep]
                col = [round(v, 1) if isinstance(v, (int, float)) else None for v in col]
                entry[aspect_row[j]] = col
                entry[aspect_row[j] + "_fstart"] = str(fstart_row[j])[:10]
        if "demand" in entry and "supply" in entry:
            entry["balance"] = [
                round(s - d, 1) if (s is not None and d is not None) else None
                for s, d in zip(entry["supply"], entry["demand"])
            ]
            out[code] = entry
    return out


def build_countries():
    sup = openpyxl.load_workbook(find("energyaspects_global-gasoline-supply_*.xlsx"), read_only=True)
    dem = openpyxl.load_workbook(find("energyaspects_global-gasoline-demand_*.xlsx"), read_only=True)
    out = {}
    pat_s = re.compile(r"gasoline supply in (.+) in kb/d$")
    pat_d = re.compile(r"gasoline demand in (.+) in kb/d$")

    def extract(wb, sheet, pat):
        if sheet not in wb.sheetnames:
            return {}, []
        rows = rows_of(wb[sheet])
        hdr = rows[0]
        dates = [str(r[0])[:10] for r in rows[1:]]
        keep = [i for i, d in enumerate(dates) if d >= START]
        res = {}
        for j, h in enumerate(hdr):
            m = pat.search(str(h)) if h else None
            if m:
                name = m.group(1)
                col = [rows[1 + i][j] for i in keep]
                res[name] = [round(v, 1) if isinstance(v, (int, float)) else None for v in col]
        return res, [dates[i] for i in keep]

    for code in REGION_NAMES:
        if code == "WORLD":
            continue
        s, sd = extract(sup, code, pat_s)
        d, dd = extract(dem, code, pat_d)
        names = sorted(set(s) | set(d))
        reg = {}
        for n in names:
            if n in REGION_NAMES.values():
                continue
            reg[n] = {"supply": s.get(n), "demand": d.get(n)}
        if reg:
            out[code] = {"dates": sd or dd, "countries": reg}
    return out


US_COLS = {
    "production": "Weekly EA forecast for MGBC refinery topdown production in United States in kb/d",
    "refinery_runs": "Weekly EA forecast for EIA refinery runs in United States in kb/d",
    "net_imports": "Weekly EA forecast for gasoline refinery topdown net imports to United States in kb/d",
    "product_supplied": "Weekly EA forecast for gasoline refinery topdown product supplied in United States in kb/d",
    "stock_change": "Weekly EA forecast for gasoline refinery topdown stock change with adjustment in United States in kb/d",
    "stocks": "Weekly EA forecast for gasoline refinery topdown closing inventories in United States in kb",
    "imports": "Weekly gasoline refinery topdown imports to United States in kb/d",
    "exports": "Weekly finished gasoline refinery topdown exports from United States in kb/d",
}
PADD_COLS = {
    "stocks": "Weekly EA forecast for gasoline refinery closing inventories in PADD {n} in kb",
    "demand": "Weekly EA forecast for gasoline refinery demand in PADD {n} in kb/d",
    "net_imports": "Weekly EA forecast for gasoline refinery net imports to PADD {n} in kb/d",
    "production": "Weekly EA forecast for gasoline refinery production in PADD {n} in kb/d",
    "stock_change": "Weekly EA forecast for gasoline refinery stock change in PADD {n} in kb/d",
}


def build_us_weekly():
    wb = openpyxl.load_workbook(find("energyaspects_us-weekly-product-stock-forecast_*.xlsx"), read_only=True)
    out = {"areas": {}}

    rows = rows_of(wb["Data"])
    hdr = [str(h) for h in rows[0]]
    dates = [str(r[0])[:10] for r in rows[1:]]
    us = {"dates": dates}
    for key, col in US_COLS.items():
        if col in hdr:
            j = hdr.index(col)
            us[key] = [round(r[j], 1) if isinstance(r[j], (int, float)) else None for r in rows[1:]]
    out["areas"]["US"] = us

    for n in range(1, 6):
        sheet = f"PADD_{n}"
        if sheet not in wb.sheetnames:
            continue
        rows = rows_of(wb[sheet])
        hdr = [str(h) for h in rows[0]]
        area = {"dates": [str(r[0])[:10] for r in rows[1:]]}
        for key, tmpl in PADD_COLS.items():
            col = tmpl.format(n=n)
            if col in hdr:
                j = hdr.index(col)
                area[key] = [round(r[j], 1) if isinstance(r[j], (int, float)) else None for r in rows[1:]]
        out["areas"][f"PADD {n}"] = area
    return out


def main():
    data = {
        "release_date": "2026-07-06",
        "as_of": "2026-07-13",
        "source": "Energy Aspects",
        "regions": build_regions(),
        "countries": build_countries(),
        "us_weekly": build_us_weekly(),
    }
    with open(OUT, "w") as f:
        json.dump(data, f)
    import os
    print("wrote", OUT, round(os.path.getsize(OUT) / 1e6, 2), "MB")
    print("regions:", list(data["regions"]))
    print("country regions:", {k: len(v["countries"]) for k, v in data["countries"].items()})
    print("us areas:", list(data["us_weekly"]["areas"]))


if __name__ == "__main__":
    main()
