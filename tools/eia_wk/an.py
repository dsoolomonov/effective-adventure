import pandas as pd, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
df=pd.read_pickle('wk.pkl')
new=dict(gas_stk=205310,gas_fin_stk=13735,gas_blend_stk=191575,gas_stk_p1=51642,gas_stk_p2=42284,gas_stk_p3=77195,gas_stk_p4=6714,gas_stk_p5=27475,gas_stk_p1a=4022,gas_stk_p1b=24428,gas_stk_p1c=23191,
gas_dem=8982,gas_prod=9750,gas_imp=281,gas_exp=926,gas_blend_imp=263,
dist_stk=104286,dist_stk_p1=21016,dist_stk_p2=25264,dist_stk_p3=44407,dist_stk_p4=3346,dist_stk_p5=10253,dist_stk_p1a=2457,dist_stk_p1b=10272,dist_stk_p1c=8287,ulsd_stk=92880,
dist_dem=3732,dist_prod=5232,dist_imp=117,dist_exp=1379,util=93.4,crude_runs=16649,gross_in=16860,util_p1=80.8,util_p2=90.2,util_p3=95.9,util_p4=100.6,util_p5=92.0,
crude_stk=412517,spr=282683,crude_prod=13269,crude_imp=5758,crude_exp=3442,jet_stk=42606,jet_dem=1813,tot_dem=21231,prop_stk=105846,resid_stk=23733,ethanol_prod=1094,ethanol_stk=24558)
T=pd.Timestamp('2026-10-16'); df.loc[T]=pd.Series(new); df=df.sort_index()
df['gas_net_exp']=df.gas_exp-df.gas_imp; df['dist_net_exp']=df.dist_exp-df.dist_imp
df['gas_days']=df.gas_stk/df.gas_dem/1; df['dist_days']=df.dist_stk/df.dist_dem
df.to_pickle('wk_full.pkl')
def same_week(col,yr,t=T):
    s=df[col].dropna(); tgt=t.replace(year=yr); i=(abs(s.index-tgt)).argmin(); return s.iloc[i]
def rep(col,fmt='{:,.0f}',div=1,ma=False):
    s=df[col]/div
    if ma: s=s.rolling(4).mean()
    c,p=s.loc[T],s.dropna().iloc[-2]
    ly=same_week(col,2025)/div if not ma else s.dropna().iloc[np.abs(s.dropna().index-T.replace(year=2025)).argmin()]
    f5=[ (same_week(col,y)/div if not ma else s.dropna().iloc[np.abs(s.dropna().index-T.replace(year=y)).argmin()]) for y in range(2021,2026)]
    print(f"{col+(' 4wk' if ma else ''):18s} {fmt.format(c):>9s} w/w {c-p:+8.1f} y/y {c-ly:+8.1f} vs5y {c-np.mean(f5):+8.1f} (5y {np.mean(f5):.1f} rng {min(f5):.1f}-{max(f5):.1f})")
for c in ['gas_stk','gas_fin_stk','gas_blend_stk','gas_stk_p1','gas_stk_p1a','gas_stk_p1b','gas_stk_p1c','gas_stk_p2','gas_stk_p3','gas_stk_p4','gas_stk_p5']: rep(c,'{:.1f}',1000)
for c in ['gas_dem','gas_prod','gas_imp','gas_exp','gas_net_exp']: rep(c); rep(c,ma=True)
rep('gas_days','{:.1f}')
for c in ['dist_stk','ulsd_stk','dist_stk_p1','dist_stk_p1a','dist_stk_p1b','dist_stk_p1c','dist_stk_p2','dist_stk_p3','dist_stk_p4','dist_stk_p5']: rep(c,'{:.1f}',1000)
for c in ['dist_dem','dist_prod','dist_imp','dist_exp','dist_net_exp']: rep(c); rep(c,ma=True)
rep('dist_days','{:.1f}')
for c in ['util','util_p1','util_p2','util_p3','util_p5','crude_runs','jet_dem','tot_dem','crude_stk']: rep(c,'{:.1f}')
# 4-week cumulative stock change
for c in ['gas_stk','dist_stk']:
    s=df[c].dropna()/1000; print(c,'4wk chg',round(s.iloc[-1]-s.iloc[-5],2),'; 5y avg same 4wk', round(np.mean([ (lambda ss: ss.iloc[-1]-ss.iloc[-5])(s[s.index<=T.replace(year=y)+pd.Timedelta(days=3)]) for y in range(2021,2026)]),2))
