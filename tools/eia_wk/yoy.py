import pandas as pd,numpy as np
df=pd.read_pickle('wk_full.pkl');T=df.index.max()
for p in ['gas','dist']:
    for k in ['dem','prod','imp','exp','net_exp']: df[f'{p}_{k}_4w']=df[f'{p}_{k}'].rolling(4).mean()
    df[f'{p}_stk_4wchg']=df[f'{p}_stk'].diff(4)
df['gas_prod_ex']=np.nan
cols=[('gas_stk','Gasoline total stocks','mb',1000),('gas_fin_stk','  Finished','mb',1000),('gas_blend_stk','  Blending comps','mb',1000),
('gas_stk_p1','  PADD1','mb',1000),('gas_stk_p1a','   1A NewEng','mb',1000),('gas_stk_p1b','   1B C.Atl','mb',1000),('gas_stk_p1c','   1C L.Atl','mb',1000),
('gas_stk_p2','  PADD2','mb',1000),('gas_stk_p3','  PADD3','mb',1000),('gas_stk_p4','  PADD4','mb',1000),('gas_stk_p5','  PADD5','mb',1000),
('gas_stk_4wchg','  4wk stock chg','mb',1000),
('gas_dem','Gas demand wk','kbd',1),('gas_dem_4w','Gas demand 4w','kbd',1),('gas_prod','Gas prod wk','kbd',1),('gas_prod_4w','Gas prod 4w','kbd',1),
('gas_imp','Gas imp wk','kbd',1),('gas_imp_4w','Gas imp 4w','kbd',1),('gas_blend_imp','Blend imp wk','kbd',1),('gas_exp','Gas exp wk','kbd',1),('gas_exp_4w','Gas exp 4w','kbd',1),
('gas_net_exp_4w','Gas netexp 4w','kbd',1),('gas_days','Gas days','d',1),
('dist_stk','Dist total stocks','mb',1000),('ulsd_stk','  ULSD','mb',1000),('dist_stk_p1','  PADD1','mb',1000),('dist_stk_p1a','   1A NewEng','mb',1000),('dist_stk_p1b','   1B C.Atl','mb',1000),('dist_stk_p1c','   1C L.Atl','mb',1000),
('dist_stk_p2','  PADD2','mb',1000),('dist_stk_p3','  PADD3','mb',1000),('dist_stk_p4','  PADD4','mb',1000),('dist_stk_p5','  PADD5','mb',1000),('dist_stk_4wchg','  4wk stock chg','mb',1000),
('dist_dem','Dist demand wk','kbd',1),('dist_dem_4w','Dist demand 4w','kbd',1),('dist_prod','Dist prod wk','kbd',1),('dist_prod_4w','Dist prod 4w','kbd',1),
('dist_imp','Dist imp wk','kbd',1),('dist_exp','Dist exp wk','kbd',1),('dist_exp_4w','Dist exp 4w','kbd',1),('dist_net_exp_4w','Dist netexp 4w','kbd',1),('dist_days','Dist days','d',1),
('util','Util %','%',1),('crude_runs','Crude runs','kbd',1),('util_p1','Util P1','%',1),('util_p2','Util P2','%',1),('util_p3','Util P3','%',1),('util_p5','Util P5','%',1)]
yrs=[2026,2025,2024,2023,2022,2021]
rows=[]
for c,l,u,dv in cols:
    s=df[c].dropna(); r={'item':l,'unit':u}
    for y in yrs:
        t=T.replace(year=y); i=np.abs(s.index-t).argmin(); r[y]=s.iloc[i]/dv if abs((s.index[i]-t).days)<=4 else np.nan
    r['5y']=np.nanmean([r[y] for y in yrs[1:]]); r['vs25']=r[2026]-r[2025]; r['vs5y']=r[2026]-r['5y']
    h=[r[y] for y in yrs[1:]]; r['rank']=1+sum(v<r[2026] for v in h if not np.isnan(v))  # 1 = lowest
    rows.append(r)
t=pd.DataFrame(rows); t.to_pickle('yoy.pkl')
pd.set_option('display.width',250)
print(t.to_string(index=False,float_format=lambda x:f'{x:,.1f}'))
print('dates',[str(df['gas_stk'].dropna().index[np.abs(df['gas_stk'].dropna().index-T.replace(year=y)).argmin()].date()) for y in yrs])
