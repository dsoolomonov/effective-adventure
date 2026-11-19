import json, re, sys
import pdfplumber

PDF = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/attachments/4a86af21-921e-4972-b649-893787c5dba6/1791459041882-asia-balances-pack.pdf"
OUT = "/home/ubuntu/crude-oil-analytics/app/asia_balances.json"

PRETTY = {"TotalAsia": "Total Asia", "Asiaex-China": "Asia ex-China", "SKorea": "S Korea", "HongKong": "Hong Kong",
          "NewZealand": "New Zealand", "TotalReported": "Total Reported"}
SUBROWS = {"Demand", "Supply", "Imports", "Exports", "power-gen", "bunkers", "feedstocks"}


def lines_of(page):
    ws = page.extract_words(x_tolerance=1.5)
    rows = {}
    for w in ws:
        rows.setdefault(round(w['top'] / 4), []).append(w)
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
    if s in ("--", "-", ""):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "")
    v = float(s)
    return -v if neg else v


def isnum(s):
    return s == "--" or re.fullmatch(r"\(?-?[\d,]+(\.\d+)?\)?", s) is not None


def parse_table(lines, ncols):
    """Country header rows (label + ncols values) followed by component rows."""
    out, cur = [], None
    for ln in lines:
        if len(ln) != ncols + 1 or not all(isnum(t) for t in ln[1:]):
            continue
        lab, vals = ln[0], [num(t) for t in ln[1:]]
        if lab in SUBROWS:
            if cur is None:
                raise ValueError(f"orphan row {ln}")
            cur["rows"][lab] = vals
        else:
            cur = {"name": PRETTY.get(lab, lab), "net": vals, "rows": {}}
            out.append(cur)
    return out


def parse_stocks(lines):
    out, cur, pending = [], None, None
    for ln in lines:
        if len(ln) == 1 and not isnum(ln[0]) and ln[0] not in ("Stocks",) and not ln[0].startswith("Source") and not ln[0].startswith("Aspects"):
            if re.fullmatch(r"[A-Za-z\-]+", ln[0]):
                cur = {"name": PRETTY.get(ln[0], ln[0]), "stocks": None, "mm": None}
                out.append(cur)
            continue
        if cur is None:
            continue
        if ln[0] == "Stocks" and len(ln) == 11:
            cur["stocks"] = [num(t) for t in ln[1:]]
        elif len(ln) == 10 and all(isnum(t) for t in ln):
            cur["stocks"] = [num(t) for t in ln]
        elif ln[0].startswith("m/m") and len(ln) == 6:
            cur["mm"] = [num(t) for t in ln[1:]]
    return [c for c in out if c["stocks"]]


def main():
    p = pdfplumber.open(PDF)
    L = [lines_of(pg) for pg in p.pages]
    hdr = " ".join(" ".join(x) for x in L[0][:3])
    m = re.search(r"(\d{1,2})\s*([A-Z][a-z]{2})\s*\|?\s*(\d{4})", " ".join(" ".join(x) for x in L[1][:1]))
    pack_date = f"{m.group(1)} {m.group(2)} {m.group(3)}" if m else None
    tm = re.search(r"Balances\s*[–-]\s*([A-Za-z]{3}\s*\d{4})", hdr.replace("|", " "))

    # margins & cracks (page 2): 9 columns
    mcols = ["2025", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
    margins = []
    group = None
    for ln in L[1]:
        j = " ".join(ln)
        if j.startswith("Singaporeunitmargins"):
            group = "Unit margins"; continue
        if j.startswith("Cracks(vsDubai)"):
            group = "Cracks vs Dubai"; continue
        if len(ln) == 10 and all(isnum(t) for t in ln[1:]):
            lab = {"refinerymargin": "Singapore average refining margin", "92RONgasoline": "92 RON gasoline",
                   "Jet/kero": "Jet/kero", "HSFO380cst": "HSFO 380 cst"}.get(ln[0], ln[0])
            margins.append({"group": group or "Refining margin", "name": lab, "vals": [num(t) for t in ln[1:]]})

    bcols = ["2025", "2026", "Sep", "Oct", "Nov", "Dec", "y/y Sep", "y/y Oct", "y/y Nov", "y/y Dec", "y/y 2026"]
    scols = ["Aug", "Sep", "Oct", "Nov", "Dec", "y/y Aug", "y/y Sep", "y/y Oct", "y/y Nov", "y/y Dec"]
    pages = {"gasoline": (2, 3, 4), "gasoil": (5, 6, 7), "kerosene": (8, 9, 10), "fueloil": ((11, 12), 13, 14)}
    products = {}
    for prod, (b, t, s) in pages.items():
        blines = sum((L[i] for i in (b if isinstance(b, tuple) else (b,))), [])
        products[prod] = {
            "balance": parse_table(blines, 11),
            "trade": parse_table(L[t], 11),
            "stocks": parse_stocks(L[s]),
        }
    # sanity: Demand - Supply vs net; Exports - Imports vs net
    issues = []
    fixes = []
    for prod, d in products.items():
        for c in d["balance"]:
            dm, sp = c["rows"].get("Demand"), c["rows"].get("Supply")
            if not (dm and sp):
                continue
            ks = [k for k in range(6) if None not in (dm[k], sp[k], c["net"][k]) and abs(c["net"][k]) > 3]
            if ks and all(abs((sp[k] - dm[k]) + c["net"][k]) <= 2.5 for k in ks):
                c["net"] = [None if v is None else -v for v in c["net"]]
                c["sign_fixed"] = True
                fixes.append(f"{prod}: {c['name']} balance printed with inverted sign in the pack; shown as supply − demand")
    for prod, d in products.items():
        for c in d["balance"]:
            dm, sp = c["rows"].get("Demand"), c["rows"].get("Supply")
            if dm and sp:
                for k in range(6):
                    if None not in (dm[k], sp[k], c["net"][k]) and abs((sp[k] - dm[k]) - c["net"][k]) > 2.5:
                        issues.append(f"{prod} bal {c['name']} col{k}: S-D {sp[k]-dm[k]} vs {c['net'][k]}")
        for c in d["trade"]:
            im, ex = c["rows"].get("Imports"), c["rows"].get("Exports")
            if im and ex:
                for k in range(6):
                    if None not in (im[k], ex[k], c["net"][k]) and abs((ex[k] - im[k]) - c["net"][k]) > 2.5:
                        issues.append(f"{prod} trade {c['name']} col{k}: X-M {ex[k]-im[k]} vs {c['net'][k]}")
    out = {"pack_date": pack_date, "title": f"Asia Product Balances – {tm.group(1) if tm else ''}".strip(),
           "balance_cols": bcols, "stock_cols": scols, "margin_cols": mcols,
           "margins": margins, "products": products, "checks": issues, "fixes": fixes, "notes": json.load(open("/home/ubuntu/asia_bal/notes.json"))}
    json.dump(out, open(OUT, "w"), indent=1)
    print("pack", pack_date, out["title"], "margins", len(margins))
    for prod, d in products.items():
        print(prod, "bal", [c["name"] for c in d["balance"]], "trade", len(d["trade"]), "stocks", [c["name"] for c in d["stocks"]])
    print("fixes", fixes); print("checks", len(issues)); print("\n".join(issues[:30]))


main()
