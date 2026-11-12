import json, pandas as pd, numpy as np

D = '/home/ubuntu/runs_bal/data/'
def m(s):
    r = json.load(open(D + s + '.json'))
    x = pd.Series({d['p']: float(d['v']) for d in r if d['v'] not in (None, '')})
    x.index = pd.PeriodIndex(x.index, freq='M')
    return x.sort_index()
def w(s):
    r = json.load(open(D + s + '.json'))
    x = pd.Series({d['p']: float(d['v']) for d in r if d['v'] not in (None, '')})
    x.index = pd.to_datetime(x.index); return x.sort_index()

gy, dy, jy = m('MGFRYUS3'), m('MDIRYUS3'), m('MKJRYUS3')
gy3, dy3, jy3 = m('MGFRYP33'), m('MDIRYP33'), m('MKJRYP33')
runs = m('MCRRIUS2')
ulsd, rbob, jet = m('EER_EPD2DXL0_PF4_RGC_DPG') * 42, m('EER_EPMRU_PF4_RGC_DPG') * 42, m('EER_EPJK_PF4_RGC_DPG') * 42
df = pd.DataFrame({'gaso': gy, 'dist': dy, 'jet': jy, 'runs': runs, 'ulsd_gaso': ulsd - rbob, 'jet_gaso': jet - rbob}).dropna(subset=['gaso', 'dist'])
df['dist+jet'] = df.dist + df.jet
df['g+d+j'] = df.gaso + df.dist + df.jet
df['yr'] = df.index.year; df['mo'] = df.index.month

print('=== Latest monthly yields (US, %)')
print(df[['gaso', 'dist', 'jet', 'dist+jet', 'g+d+j', 'runs', 'ulsd_gaso']].tail(18).round(1).to_string())

print('\n=== Annual: gasoline / distillate / jet yield, summer(Jun-Aug) vs winter(Dec-Feb) distillate & gasoline')
rows = []
for y in range(2012, 2027):
    a = df[df.yr == y]
    if len(a) == 0: continue
    s = a[a.mo.isin([6, 7, 8])]; wn = df[((df.yr == y) & (df.mo <= 2)) | ((df.yr == y - 1) & (df.mo == 12))]
    rows.append(dict(yr=y, gaso=a.gaso.mean(), dist=a.dist.mean(), jet=a.jet.mean(), dist_min=a.dist.min(), dist_max=a.dist.max(),
                     gaso_min=a.gaso.min(), gaso_max=a.gaso.max(),
                     dist_sum=s.dist.mean() if len(s) else np.nan, dist_win=wn.dist.mean() if len(wn) else np.nan,
                     gaso_sum=s.gaso.mean() if len(s) else np.nan, gaso_win=wn.gaso.mean() if len(wn) else np.nan,
                     spread=a.ulsd_gaso.mean()))
t = pd.DataFrame(rows).set_index('yr').round(1)
t['dist_swing_w-s'] = (t.dist_win - t.dist_sum).round(1); t['gaso_swing_s-w'] = (t.gaso_sum - t.gaso_win).round(1)
print(t.to_string())

print('\n=== Extremes since 2012: dist yield min/max, gaso yield min/max (month)')
for c in ['dist', 'gaso', 'jet']:
    z = df[df.yr >= 2012][c]; print(c, 'min', z.idxmin(), z.min(), 'max', z.idxmax(), z.max())

# deseasonalise & regress on spread
ds = df[df.yr >= 2012].copy()
for c in ['dist', 'gaso']:
    ds[c + '_sa'] = ds[c] - ds.groupby('mo')[c].transform('mean')
ds['spr_sa'] = ds.ulsd_gaso - ds.groupby('mo').ulsd_gaso.transform('mean')
ok = ds.dropna(subset=['spr_sa'])
b = np.polyfit(ok.spr_sa, ok.dist_sa, 1); bg = np.polyfit(ok.spr_sa, ok.gaso_sa, 1)
print(f'\n=== Price response (2012-): dist yield_sa = {b[0]:.3f} pts per $/bbl of (ULSD-gaso) spread; gaso yield_sa = {bg[0]:.3f} pts/$; corr dist={np.corrcoef(ok.spr_sa, ok.dist_sa)[0,1]:.2f}')
lag = ok.spr_sa.shift(1); mm = ~lag.isna()
print(f'   lag1: dist {np.polyfit(lag[mm], ok.dist_sa[mm], 1)[0]:.3f} pts/$, corr {np.corrcoef(lag[mm], ok.dist_sa[mm])[0,1]:.2f}')
print('   2022 (max diesel crack) months:'); print(df.loc['2022-03':'2022-12', ['gaso', 'dist', 'jet', 'ulsd_gaso']].round(1).to_string())
print('   spread range:', ok.ulsd_gaso.min().round(1), ok.ulsd_gaso.max().round(1), ' dist_sa range', ok.dist_sa.min().round(2), ok.dist_sa.max().round(2))

# max 3m and 6m change in dist yield
for n in [1, 3, 6]:
    ch = df[df.yr >= 2012].dist.diff(n); print(f'max {n}m drop in dist yield: {ch.min():.1f} pts at {ch.idxmin()};  max rise {ch.max():.1f} at {ch.idxmax()}')

print('\n=== PADD3 yields latest 12m'); print(pd.DataFrame({'gaso3': gy3, 'dist3': dy3, 'jet3': jy3}).tail(12).round(1).to_string())

# weekly current balance
print('\n=== Weekly US, latest 4wk avg (kbd) and same 4 wks last year')
ws = {k: w(k) for k in ['WDIEXUS2', 'WDIRPUS2', 'WDIUPUS2', 'WDIIMUS2', 'WDISTUS1', 'WGFRPUS2', 'WGFUPUS2', 'W_EPM0F_EEX_NUS-Z00_MBBLD', 'WGTIMUS2', 'WGTSTUS1', 'WGIRIUS2', 'WCRRIUS2', 'WDIRPP32', 'WGFRPP32']}
names = {'WDIEXUS2': 'dist exports', 'WDIRPUS2': 'dist prod', 'WDIUPUS2': 'dist demand', 'WDIIMUS2': 'dist imports', 'WDISTUS1': 'dist stocks kb',
         'WGFRPUS2': 'gaso prod', 'WGFUPUS2': 'gaso demand', 'W_EPM0F_EEX_NUS-Z00_MBBLD': 'gaso exports', 'WGTIMUS2': 'gaso imports', 'WGTSTUS1': 'gaso stocks kb',
         'WGIRIUS2': 'gross inputs', 'WCRRIUS2': 'crude runs', 'WDIRPP32': 'P3 dist prod', 'WGFRPP32': 'P3 gaso prod'}
last = ws['WDIEXUS2'].index[-1]
for k, s in ws.items():
    cur = s.iloc[-4:].mean(); ly = s[(s.index <= last - pd.Timedelta(days=364))].iloc[-4:].mean()
    print(f'{names[k]:15s} latest {s.iloc[-1]:8.0f}  4wk {cur:8.0f}  y/y 4wk {cur-ly:+7.0f}')
print('week ending', last.date())
de = ws['WDIEXUS2']; print('dist exports 2026 YTD avg', de['2026'].mean().round(0), ' 2025 avg', de['2025'].mean().round(0), ' max weekly ever', de.max(), de.idxmax().date())
print('dist exports monthly 2026:', m('MDIEXUS2')['2025-06':].round(0).to_dict()); print('P3 share of dist exports Jun-26:', (m('MDIEXP32') / m('MDIEXUS2')).iloc[-1].round(2))
print('jet exports monthly:', m('MKJEXUS2')['2026-01':].round(0).to_dict()); print('gaso exports monthly:', m('MGFEXUS2')['2026-01':].round(0).to_dict())
ds_ = ws['WDISTUS1']; print('dist stocks now', ds_.iloc[-1], ' 5y same-week range', [ds_[(ds_.index <= last - pd.Timedelta(days=364 * k))].iloc[-1] for k in range(1, 6)])
