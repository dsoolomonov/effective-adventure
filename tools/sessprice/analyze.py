from load import *
d=load(); S=['Asia','Europe','US']
res={}
for k,df in d.items():
    df=df.copy(); df['chg']=df.px.diff(); df['sess']=[session(t.hour) for t in df.index]; df['day']=[t.date() for t in df.index]
    df=df.iloc[1:]
    def ss(x): return {s:round(x[x.sess==s].chg.sum(),3) for s in S}
    wk=df[df.index>='2026-10-13']
    vol={s:float(df[df.sess==s].vol.sum()) for s in S} if df.vol.notna().any() else None
    res[k]=dict(first=d[k].px.iloc[0],last=d[k].px.iloc[-1],tot=round(d[k].px.iloc[-1]-d[k].px.iloc[0],3),sess=ss(df),wk=round(wk.chg.sum(),3),sess_wk=ss(wk),vol=vol,
                lo=d[k].px.min(),lo_t=str(d[k].px.idxmin()),hi=d[k].px.max(),hi_t=str(d[k].px.idxmax()))
for k,v in res.items():
    print(k,f"{v['first']}->{v['last']} tot {v['tot']:+} sess",v['sess'],'| wk',v['wk'],v['sess_wk'],'| hi',v['hi'],v['hi_t'][:13],'lo',v['lo'],v['lo_t'][:13], ('vol%'+str({s:round(100*x/sum(v['vol'].values())) for s,x in v['vol'].items()})) if v['vol'] else '')
# daily close (last bar per Dubai calendar day)
dc=pd.DataFrame({k:df.px.groupby(df.index.date).last() for k,df in d.items()})
dc.index=pd.to_datetime(dc.index); dch=dc.diff().dropna(how='all')
cor=dch.corr(min_periods=10).round(2)
print(cor[['B12','W23','D12','BD1','DFL1','G12','GC1','RC1','HG1']].loc[['B12','W23','D12','BD1','BD2','DFL1','G12','GC1','RC1','HG1']])
print(dc.tail(8)[['B12','W12','W23','D12','BD1','DFL1','G12','GC1','RC1','HG1']].round(2))
# WTI expiry volume crossover
v=pd.DataFrame({'W12':d['W12'].vol.groupby(d['W12'].index.date).sum(),'W23':d['W23'].vol.groupby(d['W23'].index.date).sum()}); print(v.tail(10))
json.dump(dict(res=res),open('res.json','w'),default=str)
