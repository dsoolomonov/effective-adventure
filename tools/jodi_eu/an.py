import pandas as pd, numpy as np, json
g=pd.read_parquet('sec.parquet')
EU="AT BE BG CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LT LU LV MK MT NL NO PL PT RO RS SE SI SK AL".split()
g=g[g.REF_AREA.isin(EU)]
piv=g.pivot_table(index=['ENERGY_PRODUCT','FLOW_BREAKDOWN','REF_AREA'],columns='TIME_PERIOD',values='OBS_VALUE',aggfunc='first')
months=[c for c in piv.columns if c>='2019-01']
out={}
for p in ['GASOLINE','GASDIES']:
  for f in ['TOTDEMO','REFGROUT','TOTIMPSB','TOTEXPSB','CLOSTLV']:
    s=piv.loc[(p,f)][months]
    # matched sample: countries with Aug26 and >=95% coverage since 2019
    keep=s[s['2026-08'].notna() & (s.notna().mean(axis=1)>=0.97)].index.tolist()
    miss=sorted(set(s.index)-set(keep))
    ss=s.loc[keep].ffill(axis=1).bfill(axis=1)
    tot=ss.sum()
    out[(p,f)]=dict(keep=keep,tot=tot,ss=ss)
    a,j,y=tot['2026-08'],tot['2026-07'],tot['2025-08']
    r5=[tot[f'{yy}-08'] for yy in range(2021,2026)]
    print(f"{p:8s} {f:8s} n={len(keep):2d} Aug26 {a:8.0f} Jul {j:8.0f} m/m {a-j:+7.0f} y/y {a-y:+7.0f} 5y avg {np.mean(r5):8.0f} rng {min(r5):.0f}-{max(r5):.0f}  missing:{' '.join(miss)}")
    # YTD
    ytd=[f'2026-{m:02d}' for m in range(1,9)]; ly=[f'2025-{m:02d}' for m in range(1,9)]
    if f!='CLOSTLV': print(f"   YTD26 {tot[ytd].mean():.0f} vs YTD25 {tot[ly].mean():.0f} ({tot[ytd].mean()-tot[ly].mean():+.0f})")
  # country breakdown
  for f in ['TOTDEMO','REFGROUT','TOTEXPSB','TOTIMPSB','CLOSTLV']:
    ss=out[(p,f)]['ss']
    d=(ss['2026-08']-ss['2025-08']).sort_values()
    print(' ',f,'y/y by country:',', '.join(f"{c}{v:+.0f}" for c,v in list(d.items())[:5]),' | top up:',', '.join(f"{c}{v:+.0f}" for c,v in list(d.items())[-4:]))
    print('   level Aug26 top:',', '.join(f"{c}{v:.0f}" for c,v in ss['2026-08'].sort_values(ascending=False).head(6).items()))
pd.to_pickle(out,'out.pkl')
