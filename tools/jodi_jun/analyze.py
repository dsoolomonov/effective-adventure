import pandas as pd
from calendar import monthrange

g = pd.read_parquet('gasoline.parquet')
g['OBS_VALUE'] = pd.to_numeric(g['OBS_VALUE'], errors='coerce')
g = g.dropna(subset=['OBS_VALUE'])

FLOWS = ['REFGROUT', 'TOTDEMO', 'TOTIMPSB', 'TOTEXPSB']
STOCK = 'CLOSTLV'

flow = g[(g.FLOW_BREAKDOWN.isin(FLOWS)) & (g.UNIT_MEASURE == 'KBD')]
stock = g[(g.FLOW_BREAKDOWN == STOCK) & (g.UNIT_MEASURE == 'KBBL')]
d = pd.concat([flow, stock])
piv = d.pivot_table(index=['REF_AREA', 'TIME_PERIOD'], columns='FLOW_BREAKDOWN',
                    values='OBS_VALUE', aggfunc='first')

EUROPE = ["AT","BE","BG","BY","CH","CY","CZ","DE","DK","EE","ES","FI","FR","GB","GR","HR",
          "HU","IE","IS","IT","LT","LU","LV","MD","MK","MT","NL","NO","PL","PT","RO","RS",
          "SE","SI","SK","UA","AL"]
ASIA = ["AU","BD","BN","CN","HK","ID","IN","JP","KR","MM","MY","NP","NZ","PG","PH","SG",
        "TH","TW","VN"]

CUR, PREV = '2026-06', '2026-05'
YOY = '2025-06'
HIST = [f'{y}-06' for y in range(2021, 2026)]


def series(region, flowname):
    """Per-country series for a flow, indexed by period."""
    sub = piv.loc[piv.index.get_level_values(0).isin(region), flowname].dropna()
    return sub.unstack(0) if len(sub) else pd.DataFrame()


def consistent(region, flowname, periods):
    """Sum across only the countries reporting in ALL given periods."""
    s = series(region, flowname)
    if s.empty:
        return None, []
    have = [p for p in periods if p in s.index]
    if len(have) != len(periods):
        return None, []
    sub = s.loc[periods].dropna(axis=1, how='any')
    return sub.sum(axis=1), list(sub.columns)


def report(name, region):
    print(f"\n{'='*78}\n{name} GASOLINE — June 2026 (consistent-reporter basis)\n{'='*78}")
    hdr = f"{'flow':16}{'Jun-26':>11}{'May-26':>11}{'MoM':>10}{'Jun-25':>11}{'YoY':>10}{'5yJun':>10}{'vs5y':>9}  n"
    print(hdr)
    for f in FLOWS + [STOCK]:
        mom, cm = consistent(region, f, [PREV, CUR])
        yoy, cy = consistent(region, f, [YOY, CUR])
        hist, ch = consistent(region, f, HIST + [CUR])
        if mom is None:
            print(f"{f:16}  (insufficient)")
            continue
        cur, prev = mom[CUR], mom[PREV]
        y_cur = y_prev = None
        if yoy is not None:
            y_cur, y_prev = yoy[CUR], yoy[YOY]
        h5 = hcur = None
        if hist is not None:
            h5 = hist[HIST].mean()
            hcur = hist[CUR]
        fmt = lambda v: f"{v:>11,.0f}" if v is not None else f"{'-':>11}"
        print(f"{f:16}{cur:>11,.0f}{prev:>11,.0f}{cur-prev:>10,.0f}"
              f"{(f'{y_prev:,.0f}' if y_prev is not None else '-'):>11}"
              f"{(f'{y_cur-y_prev:,.0f}' if y_prev is not None else '-'):>10}"
              f"{(f'{h5:,.0f}' if h5 is not None else '-'):>10}"
              f"{(f'{hcur-h5:,.0f}' if h5 is not None else '-'):>9}  {len(cm)}")

    # stock trajectory
    s, _ = consistent(region, STOCK, ['2026-01', '2026-02', '2026-03', '2026-04', PREV, CUR])
    if s is not None:
        print("\n  Closing-stock path (same reporters):")
        print("   " + "  ".join(f"{p[-2:]}/{v/1000:,.1f}mb" for p, v in s.items()))

    # country detail for June
    print(f"\n  Country detail (Jun-26, KBD; stocks KBBL) — MoM deltas:")
    rows = []
    for c in region:
        try:
            cur = piv.loc[(c, CUR)]
        except KeyError:
            continue
        try:
            prv = piv.loc[(c, PREV)]
        except KeyError:
            prv = None
        r = {'c': c}
        for f in FLOWS + [STOCK]:
            r[f] = cur.get(f)
            r[f + '_d'] = (cur.get(f) - prv.get(f)) if (prv is not None and pd.notna(cur.get(f)) and pd.notna(prv.get(f))) else None
        rows.append(r)
    df = pd.DataFrame(rows).set_index('c')
    df = df.sort_values('TOTDEMO', ascending=False)
    print(f"    {'':4}{'output':>9}{'Δ':>8}{'demand':>9}{'Δ':>8}{'imp':>8}{'Δ':>7}{'exp':>9}{'Δ':>8}{'stocks':>10}{'Δ':>9}")
    n = lambda v, w=9, p=0: (f"{v:>{w},.{p}f}" if pd.notna(v) and v is not None else f"{'-':>{w}}")
    for c, r in df.iterrows():
        print(f"    {c:4}{n(r.REFGROUT)}{n(r.REFGROUT_d,8)}{n(r.TOTDEMO)}{n(r.TOTDEMO_d,8)}"
              f"{n(r.TOTIMPSB,8)}{n(r.TOTIMPSB_d,7)}{n(r.TOTEXPSB)}{n(r.TOTEXPSB_d,8)}"
              f"{n(r.CLOSTLV,10)}{n(r.CLOSTLV_d,9)}")
    # who is missing June
    missing = [c for c in region if (c, CUR) not in piv.index]
    late = [c for c in region if (c, CUR) in piv.index and piv.loc[(c, CUR)].dropna().empty]
    print(f"\n  No June record: {missing}")
    print(f"  June record but all-null: {late}")


report("EUROPE", EUROPE)
report("ASIA PACIFIC", ASIA)
