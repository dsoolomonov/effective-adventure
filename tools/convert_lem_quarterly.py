import pdfplumber, json, re

PDF = "/home/ubuntu/attachments/33c614a8-5e4f-4145-b330-123d7c36fc64/1789050256652-202609_LEM_chartpack.pdf"
OUT = "/home/ubuntu/crude-oil-analytics/app/lem_quarterly.json"
QUARTERS = ["Q1'26", "Q2'26", "Q3'26", "Q4'26", "Q1'27", "Q2'27", "Q3'27", "Q4'27"]


def lines_of(page):
    ws = page.extract_words(x_tolerance=1)
    rows = {}
    for w in ws:
        rows.setdefault(round(w['top'] / 3), []).append(w)
    out = []
    for k in sorted(rows):
        toks = sorted(rows[k], key=lambda w: w['x0'])
        merged = []
        for t in toks:
            if merged and t['x0'] - merged[-1]['x1'] < 2.5:
                merged[-1] = {'text': merged[-1]['text'] + t['text'], 'x0': merged[-1]['x0'], 'x1': t['x1']}
            else:
                merged.append(dict(t))
        out.append([m['text'] for m in merged])
    return out


def num(s):
    s = s.strip()
    if s in ("--", ""):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def is_nums(tokens):
    return len(tokens) == 8 and all(t == "--" or num(t) is not None or t == "--" for t in tokens) and any(num(t) is not None for t in tokens)


PRETTY = {
    "NorthAmerica": "North America", "LatinAmerica": "Latin America", "MiddleEast": "Middle East",
    "Asia-Pacific": "Asia Pacific", "AsiaPacific": "Asia Pacific", "SaudiArabia": "Saudi Arabia",
    "UnitedStates": "United States", "UnitedKingdom": "United Kingdom", "SouthAfrica": "South Africa",
    "OtherFSU": "Other FSU", "TotalN.America": "Total", "GlobalRuns": "Global Runs",
    "NorthWestEurope": "NW Europe", "USGulfCoast": "US Gulf Coast", "USMidwest": "US Midwest",
    "PADD1": "PADD 1", "PADD2": "PADD 2", "PADD3": "PADD 3", "PADD4": "PADD 4", "PADD5": "PADD 5",
}


def parse_balance_page(lines, extra_fields=()):
    """Parse label / Demand / Supply blocks with 8 quarterly values."""
    out = {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        label = ln[0]
        if label not in ("Demand", "Supply", "RefSupply", "GPSupply", "refinerygasoline", "ethanol") \
                and not label.startswith("Q1'") and len(ln) == 9 and is_nums(ln[1:]) \
                and re.match(r"^[A-Za-z]", label):
            name = PRETTY.get(label, label)
            entry = {"balance": [num(x) for x in ln[1:]]}
            j = i + 1
            while j < len(lines) and lines[j][0] in ("Demand", "Supply", "RefSupply", "GPSupply", "refinerygasoline", "ethanol"):
                key = lines[j][0]
                field = {"Demand": "demand", "Supply": "supply", "RefSupply": "ref_supply",
                         "GPSupply": "gp_supply", "refinerygasoline": "refinery_gasoline", "ethanol": "ethanol"}[key]
                if field not in entry and len(lines[j]) == 9:
                    entry[field] = [num(x) for x in lines[j][1:]]
                j += 1
            # m/m revision block: balance revision line (8 tokens) then Demand/Supply revision lines
            if j < len(lines) and len(lines[j]) == 8 and is_nums(lines[j]):
                entry["rev_balance"] = [num(x) for x in lines[j]]
                j += 1
                while j < len(lines) and lines[j][0] in ("Demand", "Supply", "RefSupply", "GPSupply", "refinerygasoline", "ethanol"):
                    if len(lines[j]) == 9:
                        entry["rev_" + lines[j][0].lower()] = [num(x) for x in lines[j][1:]]
                    j += 1
            out[name] = entry
            i = j
        else:
            i += 1
    return out


pdf = pdfplumber.open(PDF)
pages = {i + 1: lines_of(p) for i, p in enumerate(pdf.pages)}

data = {
    "as_of": "2026-09-10",
    "pack": "Light Ends Outlook 10 Sep 2026 (Energy Aspects) — global gasoline & naphtha balances",
    "quarters": QUARTERS,
    "forecast_from": "Q3'26",
    "previous_pack": "June 2026 (13 Jul) chartpack",
    "gasoline": {
        "regions": parse_balance_page(pages[2]),
        "countries": {
            "Asia Pacific": parse_balance_page(pages[6]),
            "Middle East": parse_balance_page(pages[8]),
            "Europe": parse_balance_page(pages[9]),
            "Africa": parse_balance_page(pages[12]),
            "Latin America": parse_balance_page(pages[17]),
        },
        "us": parse_balance_page(pages[14]),
        "north_america": parse_balance_page(pages[16][:22]),
    },
    "naphtha": {
        "countries": {
            "Asia Pacific": parse_balance_page(pages[7]),
            "Europe": parse_balance_page(pages[10]),
            "Africa": parse_balance_page(pages[13]),
            "Latin America": parse_balance_page(pages[18]),
        },
        "us": parse_balance_page(pages[15]),
        "north_america": parse_balance_page(pages[16][22:]),
    },
}

# refinery runs (page 3): label + 8 numbers, values in mb/d
runs = {}
margins = {}
region = None
in_margins = False
for ln in pages[3]:
    if ln[0].startswith("Fig") and "margin" in "".join(ln).lower():
        in_margins = True
        continue
    if in_margins:
        if len(ln) == 1 and re.match(r"^[A-Za-z]", ln[0]):
            region = PRETTY.get(ln[0], re.sub(r"(?<=[a-z])(?=[A-Z])", " ", ln[0]))
        elif len(ln) == 9 and ln[0].endswith("oriented") and region and is_nums(ln[1:]):
            margins.setdefault(region, {})[ln[0]] = [num(x) for x in ln[1:]]
        continue
    if len(ln) >= 9 and is_nums(ln[-8:]):
        label = "".join(ln[:-8])
        label = PRETTY.get(label, label)
        vals = [num(x) for x in ln[-8:]]
        if vals[0] is not None and vals[0] < 100:
            runs[label] = vals
data["refinery_runs_mbd"] = runs
data["margins_usd_bbl"] = margins

# maintenance (page 4): monthly kb/d offline May26-Nov26
maint = {}
months = ["Aug 26", "Sep 26", "Oct 26", "Nov 26", "Dec 26", "Jan 27", "Feb 27"]
for ln in pages[4]:
    if len(ln) == 8 and re.match(r"^[A-Za-z]", ln[0]):
        vals = [num(x) for x in ln[1:]]
        if any(v is not None for v in vals):
            maint[PRETTY.get(ln[0], ln[0])] = vals
data["maintenance_kbd"] = {"months": months, "regions": maint}

data["ai_notes"] = json.load(open("/home/ubuntu/lem_sep_notes.json"))

with open(OUT, "w") as f:
    json.dump(data, f)

print("gasoline regions:", list(data["gasoline"]["regions"].keys()))
for r, c in data["gasoline"]["countries"].items():
    print("countries", r, list(c.keys()))
print("us:", list(data["gasoline"]["us"].keys()))
print("na:", list(data["gasoline"]["north_america"].keys()))
print("naphtha AP:", list(data["naphtha"]["countries"]["Asia Pacific"].keys()))
print("naphtha EUR:", list(data["naphtha"]["countries"]["Europe"].keys()))
print("naphtha US:", list(data["naphtha"]["us"].keys()), "NA:", list(data["naphtha"]["north_america"].keys()))
print("runs:", list(runs.keys()))
print("margins:", margins)
print("maint:", list(maint.keys()))
