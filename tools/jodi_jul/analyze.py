import pandas as pd
import numpy as np

g = pd.read_parquet('all.parquet')
g['OBS_VALUE'] = pd.to_numeric(g['OBS_VALUE'], errors='coerce')
g = g.dropna(subset=['OBS_VALUE'])
g = g[g.UNIT_MEASURE.isin(['KBD', 'KBBL'])]
flowsel = (g.FLOW_BREAKDOWN.isin(['REFGROUT', 'TOTDEMO', 'TOTIMPSB', 'TOTEXPSB']) & (g.UNIT_MEASURE == 'KBD')) | \
          ((g.FLOW_BREAKDOWN == 'CLOSTLV') & (g.UNIT_MEASURE == 'KBBL'))
g = g[flowsel]
piv = g.pivot_table(index=['ENERGY_PRODUCT', 'FLOW_BREAKDOWN', 'REF_AREA'], columns='TIME_PERIOD',
                    values='OBS_VALUE', aggfunc='first')

EUROPE = ["AT","BE","BG","CH","CY","CZ","DE","DK","EE","ES","FI","FR","GB","GR","HR",
          "HU","IE","IS","IT","LT","LU","LV","MK","MT","NL","NO","PL","PT","RO","RS",
          "SE","SI","SK","AL"]
NWE = ["BE","DE","DK","FI","FR","GB","IE","NL","NO","SE","AT","CH","PL","CZ"]
MED = ["ES","IT","GR","PT","FR","HR","SI","CY","MT","RO","BG"]

CUR, PREV, YOY = '2026-07', '2026-06', '2025-07'
HIST = [f'{y}-07' for y in range(2021, 2026)]
PRODS = ['TOTPRODS', 'GASOLINE', 'GASDIES', 'JETKERO', 'RESFUEL', 'NAPHTHA', 'LPG']
FLOWS = ['REFGROUT', 'TOTDEMO', 'TOTIMPSB', 'TOTEXPSB', 'CLOSTLV']
FN = {'REFGROUT': 'RefOut', 'TOTDEMO': 'Demand', 'TOTIMPSB': 'Imports', 'TOTEXPSB': 'Exports', 'CLOSTLV': 'Stocks(kb)'}


def agg(region, prod, flow, periods):
    try:
        s = piv.loc[(prod, flow)]
    except KeyError:
        return None, 0
    s = s[s.index.isin(region)]
    periods = list(dict.fromkeys(periods)); cols = [p for p in periods if p in s.columns]
    if len(cols) != len(periods):
        return None, 0
    s = s[cols].dropna()
    return s.sum(), len(s)


def coverage(prod, flow):
    s = piv.loc[(prod, flow)]
    s = s[s.index.isin(EUROPE)]
    have_cur = s[CUR].dropna().index.tolist()
    have_prev = s[PREV].dropna().index.tolist()
    return sorted(set(have_prev) - set(have_cur)), len(have_cur)


print("=== Coverage: Europe countries reporting Jun but NOT Jul (TOTPRODS demand)")
miss, n = coverage('TOTPRODS', 'TOTDEMO')
print(n, "report Jul; missing:", miss)

for name, region in [('EUROPE', EUROPE), ('NWE', NWE), ('MED', MED)]:
    print(f"\n===== {name} — Jul-26 (consistent reporters), ")
    rows = []
    for prod in PRODS:
        for flow in FLOWS:
            s, n = agg(region, prod, flow, [CUR, PREV, YOY] + HIST)
            if s is None or n == 0:
                continue
            cur, prev, yoy = s[CUR], s[PREV], s[YOY]
            h = s[HIST].mean()
            rows.append(dict(prod=prod, flow=FN[flow], n=n, jul=round(cur, 1), mom=round(cur - prev, 1),
                             mom_pct=round(100 * (cur - prev) / prev, 1) if prev else None,
                             yoy=round(cur - yoy, 1), yoy_pct=round(100 * (cur - yoy) / yoy, 1) if yoy else None,
                             vs5y=round(cur - h, 1), vs5y_pct=round(100 * (cur - h) / h, 1) if h else None))
    df = pd.DataFrame(rows)
    pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200)
    print(df.to_string(index=False))

print("\n===== Country movers, Europe, Jul vs Jun and vs Jul-25 (kbd) — top abs changes")
for prod in ['GASOLINE', 'GASDIES', 'JETKERO', 'TOTPRODS']:
    for flow in ['TOTDEMO', 'TOTIMPSB', 'TOTEXPSB', 'REFGROUT']:
        s = piv.loc[(prod, flow)]
        s = s[s.index.isin(EUROPE)][[CUR, PREV, YOY]].dropna()
        s = s.assign(mom=s[CUR] - s[PREV], yoy=s[CUR] - s[YOY])
        top = s.reindex(s.mom.abs().sort_values(ascending=False).index).head(6)
        print(f"\n-- {prod} {FN[flow]}: Jul | MoM | YoY")
        for c, r in top.iterrows():
            print(f"  {c}: {r[CUR]:.0f} | {r['mom']:+.0f} | {r['yoy']:+.0f}")

print("\n===== Stocks by product Europe: Jul vs Jun vs Jul-25 vs 5y range (kb), consistent reporters")
for prod in PRODS:
    s, n = agg(EUROPE, prod, 'CLOSTLV', [CUR, PREV, YOY] + HIST + [f'{y}-{m:02d}' for y in [2025] for m in range(1, 13)])
    if s is None:
        continue
    print(f"{prod}: n={n} Jul={s[CUR]:.0f} MoM={s[CUR]-s[PREV]:+.0f} YoY={s[CUR]-s[YOY]:+.0f} 5yJulAvg={s[HIST].mean():.0f} 5yJulMin={s[HIST].min():.0f} 5yJulMax={s[HIST].max():.0f}")

print("\n===== Europe gasoline monthly history 2025-01..2026-07 (consistent reporters)")
months = [f'2025-{m:02d}' for m in range(1, 13)] + [f'2026-{m:02d}' for m in range(1, 8)]
for flow in ['REFGROUT', 'TOTDEMO', 'TOTIMPSB', 'TOTEXPSB', 'CLOSTLV']:
    s, n = agg(EUROPE, 'GASOLINE', flow, months)
    if s is None: continue
    print(FN[flow], f"n={n}:", " ".join(f"{p[2:]}={v:.0f}" for p, v in s.items()))
print("\n===== Europe diesel monthly history")
for flow in ['REFGROUT', 'TOTDEMO', 'TOTIMPSB', 'TOTEXPSB', 'CLOSTLV']:
    s, n = agg(EUROPE, 'GASDIES', flow, months)
    if s is None: continue
    print(FN[flow], f"n={n}:", " ".join(f"{p[2:]}={v:.0f}" for p, v in s.items()))
print("\n===== Europe jet monthly history")
for flow in ['REFGROUT', 'TOTDEMO', 'TOTIMPSB', 'TOTEXPSB', 'CLOSTLV']:
    s, n = agg(EUROPE, 'JETKERO', flow, months)
    if s is None: continue
    print(FN[flow], f"n={n}:", " ".join(f"{p[2:]}={v:.0f}" for p, v in s.items()))

print("\n===== Revisions: Jun-26 Europe values now vs previous file (jodi_jun/gasoline.parquet) — gasoline")
try:
    old = pd.read_parquet('/home/ubuntu/jodi_jun/gasoline.parquet')
    old['OBS_VALUE'] = pd.to_numeric(old['OBS_VALUE'], errors='coerce')
    old = old[(old.TIME_PERIOD == '2026-06') & (old.UNIT_MEASURE == 'KBD') & (old.REF_AREA.isin(EUROPE))]
    new = g[(g.TIME_PERIOD == '2026-06') & (g.ENERGY_PRODUCT == 'GASOLINE') & (g.UNIT_MEASURE == 'KBD') & (g.REF_AREA.isin(EUROPE))]
    for flow in ['TOTDEMO', 'TOTIMPSB', 'TOTEXPSB', 'REFGROUT']:
        o = old[old.FLOW_BREAKDOWN == flow].set_index('REF_AREA').OBS_VALUE
        nn = new[new.FLOW_BREAKDOWN == flow].set_index('REF_AREA').OBS_VALUE
        j = pd.concat([o, nn], axis=1, keys=['old', 'new']).dropna()
        j['d'] = j.new - j.old
        big = j[j.d.abs() > 3]
        print(FN[flow], f"total rev {j.d.sum():+.0f} kbd;", ", ".join(f"{c} {r.d:+.0f}" for c, r in big.iterrows()))
except Exception as e:
    print("rev err", e)

print("\n===== Other regions quick: TOTPRODS & GASOLINE demand YoY (US, CN, IN, JP, KR, SA, BR)")
for cc in ['US', 'CN', 'IN', 'JP', 'KR', 'SA', 'BR', 'TR', 'AE', 'SG']:
    out = []
    for prod in ['TOTPRODS', 'GASOLINE', 'GASDIES', 'JETKERO']:
        try:
            s = piv.loc[(prod, 'TOTDEMO', cc)]
            if pd.notna(s.get(CUR)):
                out.append(f"{prod} {s[CUR]:.0f} ({s[CUR]-s[PREV]:+.0f} m/m, {s[CUR]-s[YOY]:+.0f} y/y)")
        except KeyError:
            pass
    print(cc, "|", "; ".join(out) if out else "no Jul data")
