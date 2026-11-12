"""ICE commitments-of-traders Excel export (data 18/19/20): 4 header rows (Category/Group/Type/Date) then weekly rows.
Returns latest week's values by group|type plus w/w change and percentile since 2020 for managed-money net/long/short."""
import openpyxl, datetime as dt


def parse(path):
    ws = openpyxl.load_workbook(path, data_only=True, read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 6: return None
    cols = []; g = None
    for c in range(len(rows[0])):
        gg = rows[1][c]; tt = rows[2][c]
        if gg: g = gg
        cols.append("date" if c == 0 else f"{g}|{tt}")
    data = []
    for r in rows[4:]:
        if not r: continue
        d = r[0]
        if not isinstance(d, (dt.date, dt.datetime)): continue
        data.append(r)
    data.sort(key=lambda r: r[0])
    name = "ice"
    for r in rows[-3:]:
        for c in (r or ()):
            if isinstance(c, str) and "request_name is" in c:
                name = c.split("request_name is")[1].split("\n")[0].strip().lower().replace("ice - ", "ice_")
    last, prev = data[-1], data[-2]
    marks, units = {}, {}
    for i, col in enumerate(cols):
        if i == 0 or last[i] is None: continue
        try: v = float(last[i])
        except: continue
        k = f"cot.{name}.{col.lower().replace(' ', '_').replace('|', '.')}"
        marks[k] = v; units[k] = "lots" if "%" not in col else "%"
        try: marks[k + ".chg"] = v - float(prev[i])
        except: pass
    # percentiles since 2020 for MM net/long/short
    for col in ("Managed Money|Net", "Managed Money|Long", "Managed Money|Short"):
        if col in cols:
            i = cols.index(col)
            hist = [float(r[i]) for r in data if r[0].year >= 2020 and r[i] is not None]
            v = float(last[i]); pct = sum(1 for h in hist if h < v) / max(1, len(hist)) * 100
            marks[f"cot.{name}.{col.lower().replace(' ', '_').replace('|', '.')}.pct2020"] = round(pct, 1)
    as_of = last[0].strftime("%Y-%m-%d")
    return "cot_xlsx", as_of, marks, units, {"name": name, "weeks": len(data)}
