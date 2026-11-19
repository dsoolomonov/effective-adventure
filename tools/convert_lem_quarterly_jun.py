import pdfplumber, json, re

PDF = "/home/ubuntu/attachments/8f74c035-e0b7-4a33-83c1-cea8345df235/1781264971432-202606+LEM+chartpack.pdf"
OUT = "/home/ubuntu/crude-oil-analytics/app/lem_quarterly.json"
QUARTERS = ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26", "Q2'26", "Q3'26", "Q4'26"]


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
            out[name] = entry
            i = j
        else:
            i += 1
    return out


pdf = pdfplumber.open(PDF)
pages = {i + 1: lines_of(p) for i, p in enumerate(pdf.pages)}

data = {
    "as_of": "2026-07-13",
    "pack": "June 2026 quarterly light-ends chartpack",
    "quarters": QUARTERS,
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
        },
    },
}

# refinery runs (page 3): label + 8 numbers, values in mb/d
runs = {}
for ln in pages[3]:
    if len(ln) >= 9 and is_nums(ln[-8:]):
        label = "".join(ln[:-8])
        label = PRETTY.get(label, label)
        vals = [num(x) for x in ln[-8:]]
        if vals[0] is not None and vals[0] < 100:
            runs[label] = vals
data["refinery_runs_mbd"] = runs

# maintenance (page 4): monthly kb/d offline May26-Nov26
maint = {}
months = ["May 26", "Jun 26", "Jul 26", "Aug 26", "Sep 26", "Oct 26", "Nov 26"]
for ln in pages[4]:
    if len(ln) == 8 and re.match(r"^[A-Za-z]", ln[0]):
        vals = [num(x) for x in ln[1:]]
        if any(v is not None for v in vals):
            maint[PRETTY.get(ln[0], ln[0])] = vals
data["maintenance_kbd"] = {"months": months, "regions": maint}

g = data["gasoline"]["regions"]
data["ai_notes"] = {
    "headline": "Q3'26 gasoline set up tight: North America, Middle East and Asia Pacific in deficit at the same time; Europe remains the world's swing surplus",
    "generated": "AI-generated analyst read of the quarterly balances (as of 2026-07-13)",
    "points": [
        "North America flips from a +221 kb/d surplus in Q1'26 to deficits of -340 (Q2) and -246 kb/d (Q3) as demand peaks near 10.6 mb/d into driving season — the region needs imports through the summer before returning to +212 in Q4.",
        "Europe stays structurally long ~830-940 kb/d every quarter — the surplus (Q3'26: +831) is the marginal barrel for the Atlantic Basin; TA arb and West Africa pull decide whether EBOB cracks hold.",
        "Middle East deficits deepen sharply to -307/-309 kb/d in Q2/Q3'26 (vs +68 a year ago) on supply losses (-227 kb/d revision in Q3) — the region turns into a demand center for Asian and European cargoes.",
        "Asia Pacific swings negative: -273 kb/d in Q2'26 and -251 in Q3 after +246 a year earlier; China supply was revised down -349 kb/d for Q3 while India stays the region's reliable exporter (+323 kb/d Q3'26).",
        "Africa's structural deficit narrows from ~-900 to ~-708/-785 kb/d as Nigerian supply ramps from 142 (Q1'25) to ~300+ kb/d — less West African import pull is a persistent headwind for European gasoline length.",
        "US PADD detail: PADD 1 remains ~2.7-2.8 mb/d short, covered by PADD 3's ~3.0 mb/d surplus plus imports; the US as a whole is only modestly long (+15 kb/d Q2'26, +148 Q3'26), so any Gulf Coast refinery hiccup tightens the East Coast fast.",
        "Global refinery runs trough at 77.9 mb/d in Q2'26 — 5.5 mb/d below a year earlier — and only recover to 80.7 in Q3; maintenance offline capacity falls from 6.1 mb/d in May to ~3.3 mb/d in July and 2.4 by November, so supply returns gradually into peak demand.",
        "Asian naphtha deficit narrows to -8,544 in Q2'26 from -14,501 a year earlier on weak Chinese/Korean cracker demand, then re-widens to -12,888 in Q3 — a soft naphtha floor caps gasoline blending economics in the East.",
    ],
    "conclusion": "Net read: the market tightens through Q3'26 — concurrent NA/ME/AP deficits against a slowly recovering run rate argue for firm gasoline cracks and backwardation into late summer; the main bear risks are Europe's persistent surplus finding fewer export outlets (Nigeria ramp) and Q4's seasonal swing back to surplus (NA +212, global balance loosening).",
}

with open(OUT, "w") as f:
    json.dump(data, f)

print("gasoline regions:", list(data["gasoline"]["regions"].keys()))
for r, c in data["gasoline"]["countries"].items():
    print("countries", r, list(c.keys()))
print("us:", list(data["gasoline"]["us"].keys()))
print("na:", list(data["gasoline"]["north_america"].keys()))
print("naphtha AP:", list(data["naphtha"]["countries"]["Asia Pacific"].keys()))
print("naphtha EUR:", list(data["naphtha"]["countries"]["Europe"].keys()))
print("runs:", list(runs.keys()))
print("maint:", list(maint.keys()))
