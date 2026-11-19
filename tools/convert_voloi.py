import json
from datetime import datetime
import openpyxl

SRC = "/home/ubuntu/attachments/52c2a95c-6730-4c82-8b01-c23e3438918c/Energy_Volume_OI_Tracker.xlsx"
OUT = "/home/ubuntu/crude-oil-analytics/app/voloi.json"

INTRADAY = {
    "CO1": {"sheet": "CO1_3min", "commodity": "Brent", "label": "Brent CO1 (front)", "unit": "$/bbl"},
    "CO2": {"sheet": "CO2_3min", "commodity": "Brent", "label": "Brent CO2 (2nd)", "unit": "$/bbl"},
    "XB1": {"sheet": "XB1_3min", "commodity": "RBOB", "label": "RBOB XB1 (front)", "unit": "¢/gal"},
    "XB2": {"sheet": "XB2_3min", "commodity": "RBOB", "label": "RBOB XB2 (2nd)", "unit": "¢/gal"},
    "QS1": {"sheet": "QS1_3min", "commodity": "Gasoil", "label": "Gasoil QS1 (front)", "unit": "$/t"},
    "QS2": {"sheet": "QS2_3min", "commodity": "Gasoil", "label": "Gasoil QS2 (2nd)", "unit": "$/t"},
}
OI_SHEETS = {
    "Brent": {"sheet": "Brent_Daily_OI", "unit": "$/bbl", "c1": "CO1", "c2": "CO2"},
    "RBOB": {"sheet": "RBOB_Daily_OI", "unit": "¢/gal", "c1": "XB1", "c2": "XB2"},
    "Gasoil": {"sheet": "Gasoil_Daily_OI", "unit": "$/t", "c1": "QS1", "c2": "QS2"},
}


def isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
    intraday = {}
    for code, meta in INTRADAY.items():
        ws = wb[meta["sheet"]]
        rows = list(ws.iter_rows(values_only=True))
        t, p, v = [], [], []
        for r in rows[3:]:  # data starts row 4 (0-idx 3)
            if not r or not isinstance(r[0], datetime):
                continue
            if not isnum(r[1]) or not isnum(r[2]):
                continue
            t.append(r[0].strftime("%Y-%m-%dT%H:%M"))
            p.append(round(float(r[1]), 4))
            v.append(int(r[2]))
        intraday[code] = {"commodity": meta["commodity"], "label": meta["label"],
                          "unit": meta["unit"], "t": t, "p": p, "v": v}
        print("%s: %d bars  %s..%s" % (code, len(t), t[0] if t else "-", t[-1] if t else "-"))

    oi = {}
    for comm, meta in OI_SHEETS.items():
        ws = wb[meta["sheet"]]
        rows = list(ws.iter_rows(values_only=True))
        data = rows[3:]  # newest-first
        contracts = []
        for base, code in ((0, meta["c1"]), (5, meta["c2"])):
            recs = []
            for r in data:
                if base >= len(r):
                    continue
                d = r[base]
                if not isinstance(d, datetime):
                    continue
                px = r[base + 1] if base + 1 < len(r) else None
                oiv = r[base + 2] if base + 2 < len(r) else None
                recs.append((d, float(px) if isnum(px) else None, int(oiv) if isnum(oiv) else None))
            recs.sort(key=lambda x: x[0])  # oldest-first
            contracts.append({
                "code": code,
                "dates": [d.strftime("%Y-%m-%d") for d, _, _ in recs],
                "px": [px for _, px, _ in recs],
                "oi": [o for _, _, o in recs],
            })
        oi[comm] = {"unit": meta["unit"], "contracts": contracts}
        n = len(contracts[0]["dates"])
        print("OI %s: %d days  %s..%s" % (comm, n, contracts[0]["dates"][0], contracts[0]["dates"][-1]))

    # anchor = latest intraday timestamp
    all_t = [intraday[c]["t"][-1] for c in intraday if intraday[c]["t"]]
    anchor = max(all_t) if all_t else None
    out = {"as_of": anchor, "intraday": intraday, "oi": oi}
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    import os
    print("size", round(os.path.getsize(OUT) / 1024), "KB")


if __name__ == "__main__":
    main()
