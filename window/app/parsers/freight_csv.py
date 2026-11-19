"""GFI / Clarksons CSV exports: source,periodType,date,instrument,period,uom,value. Stored as marks keyed
instrument.periodType.period with unit = uom; as_of = file date. Returns one record per (date) in the file."""
import csv, io


def parse(path_or_name, text=None):
    rows = []
    if text and "source," in text[:200]:
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        with open(path_or_name, newline="") as f: rows = list(csv.DictReader(f))
    if not rows: return None
    by_date = {}
    for r in rows:
        try: v = float(r["value"])
        except: continue
        key = f"{r['instrument']}.{r['periodType']}.{r['period']}"
        by_date.setdefault(r["date"], {})[key] = (v, r["uom"])
    as_of = max(by_date)
    src = rows[0]["source"].lower()
    marks = {k: v for k, (v, u) in by_date[as_of].items()}
    units = {k: u.lower() for k, (v, u) in by_date[as_of].items()}
    meta = {"dates": sorted(by_date), "source": src, "n_rows": len(rows)}
    return "freight_csv", as_of, marks, units, meta
