import pandas as pd

g = pd.read_csv('NewProcedure_Primary_CSV.csv', dtype=str)
g['OBS_VALUE'] = pd.to_numeric(g['OBS_VALUE'], errors='coerce')
g = g.dropna(subset=['OBS_VALUE'])
print(g.ENERGY_PRODUCT.unique(), g.FLOW_BREAKDOWN.unique(), g.UNIT_MEASURE.unique())
print('latest period', g.TIME_PERIOD.max())
g.to_parquet('primary.parquet')

sel = g[(g.ENERGY_PRODUCT == 'CRUDEOIL') & (g.UNIT_MEASURE.isin(['KBD', 'KBBL']))]
sel = sel[((sel.FLOW_BREAKDOWN != 'CLOSTLV') & (sel.UNIT_MEASURE == 'KBD')) |
          ((sel.FLOW_BREAKDOWN == 'CLOSTLV') & (sel.UNIT_MEASURE == 'KBBL'))]
piv = sel.pivot_table(index=['REF_AREA', 'FLOW_BREAKDOWN'], columns='TIME_PERIOD', values='OBS_VALUE', aggfunc='first')

months = [f'2025-{m:02d}' for m in range(1, 13)] + [f'2026-{m:02d}' for m in range(1, 8)]
hist = [f'{y}-07' for y in range(2021, 2026)]
for c in ['SA', 'CN', 'US', 'IN', 'AE', 'IQ', 'KW', 'RU', 'KR', 'JP']:
    print(f'\n===== {c} crude')
    try:
        s = piv.loc[c]
    except KeyError:
        print('none'); continue
    for fl in s.index:
        row = s.loc[fl]
        cur = row.get('2026-07'); prev = row.get('2026-06'); yoy = row.get('2025-07')
        h = row[[x for x in hist if x in row.index]].mean()
        print(f'{fl:10s} Jul26={cur} m/m={None if cur is None or pd.isna(cur) or pd.isna(prev) else round(cur-prev,1)} y/y={None if pd.isna(cur) or pd.isna(yoy) else round(cur-yoy,1)} vs5y={None if pd.isna(cur) else round(cur-h,1)}')
        print('   ', ' '.join(f"{m[2:]}={row[m]:.0f}" for m in months if m in row.index and not pd.isna(row[m])))
