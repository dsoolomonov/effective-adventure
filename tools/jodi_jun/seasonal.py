import pandas as pd

g = pd.read_parquet('gasoline.parquet')
g['OBS_VALUE'] = pd.to_numeric(g['OBS_VALUE'], errors='coerce')
g = g.dropna(subset=['OBS_VALUE'])
FLOWS = ['REFGROUT', 'TOTDEMO', 'TOTIMPSB', 'TOTEXPSB']
flow = g[(g.FLOW_BREAKDOWN.isin(FLOWS)) & (g.UNIT_MEASURE == 'KBD')]
stock = g[(g.FLOW_BREAKDOWN == 'CLOSTLV') & (g.UNIT_MEASURE == 'KBBL')]
piv = pd.concat([flow, stock]).pivot_table(index=['REF_AREA', 'TIME_PERIOD'],
                                          columns='FLOW_BREAKDOWN', values='OBS_VALUE', aggfunc='first')

EUROPE = ["AT","BE","BG","BY","CH","CY","CZ","DE","DK","EE","ES","FI","FR","GB","GR","HR",
          "HU","IE","IS","IT","LT","LU","LV","MD","MK","MT","NL","NO","PL","PT","RO","RS",
          "SE","SI","SK","UA","AL"]
ASIA = ["AU","BD","BN","CN","HK","ID","IN","JP","KR","MM","MY","NP","NZ","PG","PH","SG",
        "TH","TW","VN"]


def ser(region, f):
    s = piv.loc[piv.index.get_level_values(0).isin(region), f].dropna()
    return s.unstack(0)


def pair_change(region, f, p_may, p_jun):
    s = ser(region, f)
    if p_may not in s.index or p_jun not in s.index:
        return None
    sub = s.loc[[p_may, p_jun]].dropna(axis=1, how='any')
    return sub.loc[p_jun].sum() - sub.loc[p_may].sum()


for name, region in [("EUROPE", EUROPE), ("ASIA PACIFIC", ASIA)]:
    print(f"\n=== {name}: May->June change by year (consistent reporters within each year) ===")
    print(f"{'yr':6}{'demand Δ':>12}{'output Δ':>12}{'exports Δ':>12}{'stocks Δ(mb)':>14}")
    for y in range(2019, 2027):
        row = [pair_change(region, f, f'{y}-05', f'{y}-06') for f in ['TOTDEMO', 'REFGROUT', 'TOTEXPSB']]
        st = pair_change(region, 'CLOSTLV', f'{y}-05', f'{y}-06')
        fm = lambda v, w=12, p=0: (f"{v:>{w},.{p}f}" if v is not None else f"{'-':>{w}}")
        print(f"{y:<6}{fm(row[0])}{fm(row[1])}{fm(row[2])}{fm(st/1000 if st is not None else None,14,2)}")

    print(f"\n  --- {name} June YoY by country (demand KBD) ---")
    s = ser(region, 'TOTDEMO')
    for c in sorted(region):
        if c not in s.columns:
            continue
        cur = s[c].get('2026-06')
        prv = s[c].get('2025-06')
        if pd.notna(cur) and pd.notna(prv):
            print(f"    {c:4}{cur:>9,.0f}{prv:>9,.0f}{cur-prv:>9,.0f}{(cur/prv-1)*100:>8.1f}%")
