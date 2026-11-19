import csv, json, collections
from datetime import datetime

SRC = "/home/ubuntu/attachments/eb55512d-aee6-4f4a-b65b-55d255e17d81/fujairah_ara_japan_singapore_product_stocks_history.csv"
OUT = "/home/ubuntu/crude-oil-analytics/app/product_stocks.json"
ANCHOR = "2026-07-15"
MIN_DATE = "2015-01-01"

REGION_ORDER = ["Fujairah", "ARA", "Japan", "Singapore"]
REGION_ID = {"Fujairah": "fujairah", "ARA": "ara", "Japan": "japan", "Singapore": "singapore"}
REGION_UNIT = {"Fujairah": "mmbbl", "ARA": "kt", "Japan": "mmbbl", "Singapore": "mmbbl"}

# tidy long product-group labels
RENAME = {
    "Enterprise Singapore Lt Distillates Singapore Stocks": "Light distillates",
    "Enterprise Singapore Mid Distillates Singapore Stocks": "Middle distillates",
    "Light distillates / light ends": "Light distillates",
    "Middle distillates": "Middle distillates",
    "Heavy distillates / residues": "Heavy distillates / residues",
}


def pdate(s):
    return datetime.strptime(s, "%d/%m/%Y").date()


def num(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def pct(v, arr):
    a = sorted(x for x in arr if x is not None)
    if not a:
        return None
    below = sum(1 for x in a if x <= v)
    return round(100.0 * below / len(a))


def fmt(v, unit):
    if v is None:
        return "n/a"
    return ("%.1f %s" % (v, "mmbbl" if unit == "mmbbl" else "kt"))


def analysis(region, products):
    """Data-driven retrospective for the region's product stocks."""
    unit = REGION_UNIT[region]
    lines = []
    for p in products:
        dts, vals = p["dates"], p["values"]
        pairs = [(d, v) for d, v in zip(dts, vals) if v is not None]
        if len(pairs) < 8:
            continue
        latest_d, latest = pairs[-1]
        wow = latest - pairs[-2][1]
        # ~4 weeks ago
        m4 = latest - pairs[-5][1] if len(pairs) >= 5 else None
        # year ago (closest to 52 weeks back)
        yoy = None
        if len(pairs) >= 53:
            yoy = latest - pairs[-53][1]
        last52 = [v for _, v in pairs[-52:]]
        p5 = pct(latest, [v for _, v in pairs[-260:]])
        rng = ""
        if last52:
            rng = " · 52w range %.1f–%.1f" % (min(last52), max(last52))
        yoytxt = (", YoY %+.1f" % yoy) if yoy is not None else ""
        m4txt = (", 4w %+.1f" % m4) if m4 is not None else ""
        p5txt = (" · ~%d%%ile of 5y" % p5) if p5 is not None else ""
        lines.append("%s: %s (WoW %+.1f%s%s)%s%s"
                     % (p["name"], fmt(latest, unit), wow, m4txt, yoytxt, rng, p5txt))
    hdr = ("%s product stocks — latest week %s, values in %s. "
           % (region, products[0]["last"], "million barrels" if unit == "mmbbl" else "thousand tonnes"))
    return hdr + " | ".join(lines)


def main():
    rows = list(csv.DictReader(open(SRC)))
    grp = collections.defaultdict(list)
    for r in rows:
        grp[(r["region"], r["product_group"])].append(r)

    regions = []
    for reg in REGION_ORDER:
        products = []
        keys = sorted(k for k in grp if k[0] == reg)
        for k in keys:
            rs = grp[k]
            pairs = []
            for r in rs:
                d = pdate(r["assessDate"]).isoformat()
                if d < MIN_DATE:
                    continue
                v = num(r["chart_value"])
                pairs.append((d, v))
            pairs.sort()
            # dedupe by date (keep last)
            dd = {}
            for d, v in pairs:
                dd[d] = v
            dts = sorted(dd)
            vals = [dd[d] for d in dts]
            if not dts:
                continue
            name = RENAME.get(k[1], k[1])
            products.append({
                "name": name,
                "symbol": rs[0]["symbol"],
                "dates": dts,
                "values": vals,
                "last": dts[-1],
            })
        products.sort(key=lambda p: p["name"])
        an = analysis(reg, products)
        for p in products:
            del p["last"]
        regions.append({
            "id": REGION_ID[reg],
            "name": reg,
            "unit": REGION_UNIT[reg],
            "products": products,
            "analysis": an,
        })

    out = {"as_of": ANCHOR, "regions": regions}
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    for r in regions:
        print("%-10s unit=%-6s products=%d  range %s..%s"
              % (r["id"], r["unit"], len(r["products"]),
                 r["products"][0]["dates"][0], r["products"][0]["dates"][-1]))
    import os
    print("size", round(os.path.getsize(OUT) / 1024), "KB")


if __name__ == "__main__":
    main()
