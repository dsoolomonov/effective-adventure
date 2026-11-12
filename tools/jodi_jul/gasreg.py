import pandas as pd

g = pd.read_parquet('all.parquet')
g['OBS_VALUE'] = pd.to_numeric(g['OBS_VALUE'], errors='coerce')
g = g.dropna(subset=['OBS_VALUE'])
g = g[g.ENERGY_PRODUCT == 'GASOLINE']
g = g[((g.FLOW_BREAKDOWN.isin(['REFGROUT', 'TOTDEMO', 'TOTIMPSB', 'TOTEXPSB'])) & (g.UNIT_MEASURE == 'KBD')) |
      ((g.FLOW_BREAKDOWN == 'CLOSTLV') & (g.UNIT_MEASURE == 'KBBL'))]
piv = g.pivot_table(index=['FLOW_BREAKDOWN', 'REF_AREA'], columns='TIME_PERIOD', values='OBS_VALUE', aggfunc='first')

REG = {
 'Europe': "AT BE BG CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LT LU LV MK MT NL NO PL PT RO RS SE SI SK AL".split(),
 'N.America': "US CA MX".split(),
 'LatAm': "AR BR CL CO EC PE VE TT BO PY UY CR GT HN NI PA SV DO JM CU".split(),
 'Middle East': "SA AE IQ IR KW QA OM BH JO LB IL SY YE".split(),
 'Asia-Pac': "CN IN JP KR TW SG TH ID MY PH VN AU NZ PK BD LK MM KH BN HK MN".split(),
 'Africa': "DZ EG LY MA NG ZA TN AO CI GH KE MZ SN TZ CM GA SD CG".split(),
 'FSU': "RU KZ AZ BY UA UZ TM GE AM KG TJ MD".split(),
}
CUR, PREV, YOY = '2026-07', '2026-06', '2025-07'
HIST = [f'{y}-07' for y in range(2021, 2026)]
FL = [('TOTDEMO', 'Demand'), ('REFGROUT', 'RefOut'), ('TOTIMPSB', 'Imports'), ('TOTEXPSB', 'Exports'), ('CLOSTLV', 'Stocks kb')]

for r, cc in REG.items():
    print(f'\n===== {r}')
    d = piv.loc['TOTDEMO']; d = d[d.index.isin(cc)]
    have = d[CUR].dropna().index.tolist()
    jun = d[PREV].dropna().index.tolist()
    missing_jul = sorted(set(jun) - set(have))
    never = sorted(set(cc) - set(d.index) - set(d[d[YOY].notna()].index))
    print('reporters Jul:', len(have), ' missing Jul (had Jun):', missing_jul)
    stale = {c: d.loc[c].dropna().index.max() for c in cc if c in d.index and c not in have}
    print('last period for non-reporters:', stale)
    for fl, name in FL:
        s = piv.loc[fl]; s = s[s.index.isin(cc)]
        cols = [CUR, PREV, YOY] + HIST
        s2 = s[[c for c in dict.fromkeys(cols) if c in s.columns]].dropna(subset=[CUR, PREV, YOY])
        if len(s2) == 0:
            print(f'{name:10s} no data'); continue
        cur, prev, yoy = s2[CUR].sum(), s2[PREV].sum(), s2[YOY].sum()
        h = s2[[c for c in HIST if c in s2.columns]].dropna().sum(axis=0).mean() if all(c in s2.columns for c in HIST) else float('nan')
        print(f'{name:10s} n={len(s2):2d} {cur:9.0f}  m/m {cur-prev:+7.0f} ({(cur/prev-1)*100:+.1f}%)  y/y {cur-yoy:+7.0f} ({(cur/yoy-1)*100:+.1f}%)  vs5y {cur-h:+7.0f} ({(cur/h-1)*100:+.1f}%)')
        # top movers
        mv = (s2[CUR] - s2[YOY]).sort_values()
        print('     y/y movers:', ', '.join(f'{k} {v:+.0f}' for k, v in list(mv.head(3).items()) + list(mv.tail(3).items())),
              '| m/m:', ', '.join(f'{k} {v:+.0f}' for k, v in (s2[CUR]-s2[PREV]).sort_values().pipe(lambda x: list(x.head(2).items())+list(x.tail(2).items()))))

print('\n===== Key countries gasoline (Jul26, m/m, y/y)')
for c in "US CA MX BR AR CO CN IN JP KR TW SG TH ID MY AU SA AE KW IQ EG NG DZ ZA RU KZ TR".split():
    row = []
    for fl, name in FL:
        try:
            s = piv.loc[(fl, c)]
        except KeyError:
            row.append(f'{name}: -'); continue
        cur = s.get(CUR)
        if pd.isna(cur):
            last = s.dropna().index.max() if s.notna().any() else None
            row.append(f'{name}: NA(last {last})'); continue
        row.append(f'{name}: {cur:.0f} ({cur-s.get(PREV):+.0f} m/m, {cur-s.get(YOY):+.0f} y/y)')
    print(c, ' | '.join(row))
