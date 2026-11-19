import json, pandas as pd, numpy as np
raw=json.load(open('/home/ubuntu/xmove/raw.json'))
BAR={'NOvDFL':0.5,'dECDFL':0.5,'BRENT DUBAI nov':None,'Brent Dubai Dec':None}
def ser(k):
    L=BAR.get(k,4.0)
    df=pd.DataFrame(raw[k],columns=['ts','px','vol']); df.ts=pd.to_datetime(df.ts)
    df=df.drop_duplicates('ts',keep='last').set_index('ts').sort_index()
    if L: df.index=df.index+pd.Timedelta(hours=L)   # close time, Dubai
    return df.px
S={k:ser(k) for k in raw}
S['QS1b']=S['QS1']/7.45; S['QS2b']=S['QS2']/7.45
S['GOcrkNov']=(S['QS1b']-S['CO1']).dropna()
S['DubMinusBrentStruct']=(S['DubaiM1M2']-S['BRENTM1M2']).dropna()
def at(s,t):
    x=s[s.index<=t]; return (float(x.iloc[-1]),x.index[-1]) if len(x) else (None,None)
B0=pd.Timestamp('2026-10-22 02:00'); B1=pd.Timestamp('2026-10-23 02:00'); W0=pd.Timestamp('2026-10-19 02:00'); E=pd.Timestamp('2026-10-23 18:00')
print(f"{'key':22}{'21Oct':>9}{'22Oct':>9}{'yday':>8}{'today':>8}{'wk':>8}{'last':>9}")
for k in ['CO1','CO2','QS1','QS1b','QS2','QS1QS2','GOcrkNov','Gasoil Crack Dec','BRENTM1M2','BrentM2M3','BrentM1M3','WTIM1M2','WTIM2M3','WTIM1M3','DubaiM1M2','DubaiM2M3','DubaiM1M3','DubMinusBrentStruct','NOvDFL','dECDFL','BRENT DUBAI nov','Brent Dubai Dec']:
    s=S[k]; a,_=at(s,B0); b,_=at(s,B1); w,_=at(s,W0); l,lt=at(s,E)
    print(f"{k:22}{a:9.2f}{b:9.2f}{b-a:+8.2f}{l-b:+8.2f}{l-w:+8.2f}{l:9.2f} {lt}")
# yesterday by session using close-time interpolation on 2h grid
def grid(s,step='2h'):
    g=pd.date_range(s.index[0].floor('2h'),s.index[-1],freq=step)
    u=s.reindex(s.index.union(g)).interpolate('time',limit_area='inside')
    # no interpolation over gaps>8h
    prev=pd.Series(s.index,index=s.index).reindex(u.index,method='ffill'); nxt=pd.Series(s.index,index=s.index).reindex(u.index,method='bfill')
    u[(nxt-prev)>pd.Timedelta(hours=8)]=np.nan
    u[s.index.intersection(u.index)]=s
    return u.reindex(g)
G={k:grid(S[k]) for k in S if k not in ('BRENT DUBAI nov','Brent Dubai Dec')}
print('\nyesterday 22 Oct by session (Asia 02-10, Europe 10-18, US 18-02 Dubai):')
for k in ['CO1','QS1b','GOcrkNov','Gasoil Crack Dec','QS1QS2','BRENTM1M2','WTIM1M2','DubaiM1M2','DubaiM1M3','NOvDFL','dECDFL']:
    g=G[k]; v=[g.get(pd.Timestamp(f'2026-10-22 {h}')) for h in ('02:00','10:00','18:00')]+[g.get(pd.Timestamp('2026-10-23 02:00'))]
    v=[float(x) if x is not None and not pd.isna(x) else np.nan for x in v]
    print(f"{k:18} Asia {v[1]-v[0]:+6.2f} Eur {v[2]-v[1]:+6.2f} US {v[3]-v[2]:+6.2f}")
# lead-lag: corr(dCO1(t), dX(t+k)) on 4h changes sampled on 2h grid
print('\nlead-lag vs CO1 4h changes (k>0: X moves AFTER Brent), since 25 Sep:')
c=G['CO1'].diff(2)
for k in ['QS1b','GOcrkNov','Gasoil Crack Dec','QS1QS2','BRENTM1M2','WTIM1M2','DubaiM1M2','DubaiM1M3','NOvDFL','dECDFL','DubMinusBrentStruct']:
    x=G[k].diff(2); r={}
    for lag in range(-6,7):
        d=pd.concat([c,x.shift(-lag)],axis=1).dropna(); d=d[(d.iloc[:,0]!=0)|(d.iloc[:,1]!=0)]
        r[lag*2]=d.corr().iloc[0,1] if len(d)>20 else np.nan
    best=max(r,key=lambda z:abs(r[z]) if not pd.isna(r[z]) else -1)
    d=pd.concat([c,x.shift(-best//2)],axis=1).dropna(); beta=np.polyfit(d.iloc[:,0],d.iloc[:,1],1)[0]
    print(f"{k:20} peak lag {best:+3d}h r={r[best]:+.2f} beta={beta:+.3f} | "+' '.join(f"{l:+d}:{v:+.2f}" for l,v in r.items() if abs(l)<=8))
json.dump({k:[[str(t),float(v)] for t,v in s.items()] for k,s in S.items()},open('/home/ubuntu/xmove/close.json','w'))
