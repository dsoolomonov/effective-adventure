from load import *
d=load()
WIN='2026-10-02 02:00'; WK='2026-10-13 00:00'; S4=['Asia','Europe','US','Wknd gap']
def bars(k):
    df=d[k].copy(); df['gap']=df.index.to_series().diff().dt.total_seconds()/3600; df['chg']=df.px.diff()
    df['sess']=[('Wknd gap' if g>12 else session(t.hour)) for t,g in zip(df.index,df.gap)]
    return df.iloc[1:]
inst=[];out={}
for sh,(k,lab,ctr,grp,unit) in META.items():
    raw=d[k]; b=bars(k); bw=b[b.index>=WIN]; bk=b[b.index>=WK]
    sd=float(bw.chg.std())
    base=raw[raw.index<WIN].px.iloc[-1] if (raw.index<WIN).any() else raw.px.iloc[0]
    basewk=raw[raw.index<WK].px.iloc[-1]
    ss=lambda x:{s:round(float(x[x.sess==s].chg.sum()),3) for s in S4}
    vol={s:float(bw[bw.sess==s].vol.sum()) for s in S4} if raw.vol.notna().any() else None
    hv=None
    if vol: hv={int(h):float(bw[[t.hour==h for t in bw.index]].vol.sum()) for h in range(0,24,2)}
    dd=bw.copy(); dd['day']=[str((t-pd.Timedelta(hours=2)).date()) for t in dd.index]
    dayx=dd.pivot_table(index='day',columns='sess',values='chg',aggfunc='sum').round(3)
    inst.append(dict(key=k,label=lab,contract=ctr,group=grp,unit=unit,sheet=sh,last=float(raw.px.iloc[-1]),last_ts=str(raw.index[-1]),
        base=float(base),chg_win=round(float(raw.px.iloc[-1]-base),3),chg_wk=round(float(raw.px.iloc[-1]-basewk),3),sd2h=round(sd,4),
        sess_win=ss(bw),sess_wk=ss(bk),vol_sess=vol,vol_hour=hv,
        hi=float(raw[raw.index>=WIN].px.max()),lo=float(raw[raw.index>=WIN].px.min()),
        dayx={day:{s:(None if pd.isna(r.get(s)) else float(r.get(s))) for s in S4 if s in r} for day,r in dayx.iterrows()},
        series=[[str(t)[:16],float(p),(None if pd.isna(v) else float(v))] for t,p,v in zip(raw.index,raw.px,raw.vol)]))
dc=pd.DataFrame({k:df.px.groupby((df.index-pd.Timedelta(hours=2)).date).last() for k,df in d.items()}); dc.index=pd.to_datetime(dc.index)
dc=dc[dc.index>='2026-10-01']; dch=dc.diff().iloc[1:]
dch=dch[[x.weekday()<5 for x in dch.index]]  # drop Saturday stub closes
cor=dch.corr(min_periods=8).round(2)
keys=[i['key'] for i in inst]
out=dict(window_start=WIN,week_start=WK,asof=max(i['last_ts'] for i in inst),instruments=inst,
    corr=dict(keys=keys,m=[[None if pd.isna(cor.loc[a,b]) else float(cor.loc[a,b]) for b in keys] for a in keys],ndays=int(len(dch))))
json.dump(out,open('sess.json','w'),default=str)
for i in inst: print(f"{i['key']:5} last {i['last']:8.2f} win {i['chg_win']:+7.2f} wk {i['chg_wk']:+7.2f} sd {i['sd2h']:.2f} | "+' '.join(f"{s[:2]} {v:+.2f}" for s,v in i['sess_win'].items())+' | wk '+' '.join(f"{s[:2]} {v:+.2f}" for s,v in i['sess_wk'].items())+(' vol%'+','.join(str(round(100*v/sum(i['vol_sess'].values()))) for v in i['vol_sess'].values()) if i['vol_sess'] else ''))
print('ndays',len(dch))
print(cor.loc[['B12','W23','D12','BD1','BD2','DFL1','DFL2','G12','GC1','RC1','HG1'],['B12','D12','BD1','DFL1','G12','GC1','RC1','HG1']])
import openpyxl
wb=openpyxl.load_workbook('lo/Brent_session_analysis_20Oct.xlsx',data_only=True)
out['research']=[dict(theme=r[0],source=r[1],says=r[2],key=r[3],horizon=r[4],sign=r[5],chg=r[6],unit=r[7],driver=r[8],verdict=r[9]) for r in wb['Research'].iter_rows(min_row=5,max_row=13,values_only=True)]
out['research_score']=wb['Research']['B15'].value
out['read']=[r[0] for r in wb['Read'].iter_rows(min_row=3,max_row=12,values_only=True) if r[0]]
out['validation']=wb['Validation']['B2'].value
out['contracts']=['CO1 = Brent Dec (crack reference)','WTI Nov expires 20 Oct → Dec/Jan is the front','Dubai M1 = Nov','Gasoil QS1 = Nov, cracks vs Dec Brent','HO-GO M1 = Nov','RBOB-Brent vs Dec Brent','Times = Dubai (UTC+4)']
out['sessions_def']={'Asia':[2,10],'Europe':[10,18],'US':[18,2],'gap_hours':12}
json.dump(out,open('/home/ubuntu/crude-oil-analytics/app/session_pricing.json','w'),default=str)
print('json ok',out['validation'],out['research_score'])
