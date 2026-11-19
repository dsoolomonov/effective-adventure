"""Builds app/cross_moves_intraday.json from the Bloomberg intraday export (Dubai time, bar-start stamps)."""
import json, sys, openpyxl, pandas as pd, numpy as np
SRC=sys.argv[1] if len(sys.argv)>1 else '/home/ubuntu/xmove/src.xlsx'
OUT='/home/ubuntu/crude-oil-analytics/app/cross_moves_intraday.json'
# sheet -> key, label, group, unit, bar hours (None = daily)
META={'CO1':('co1','Brent Dec (CO1)','flat','$/bbl',4),'CO2':('co2','Brent Jan (CO2)','flat','$/bbl',4),
 'QS1':('qs1','ICE Gasoil Nov (QS1)','flat','$/t',4),'QS2':('qs2','ICE Gasoil Dec (QS2)','flat','$/t',4),
 'QS1QS2':('g12','Gasoil Nov/Dec','prodspread','$/t',4),'Gasoil Crack Dec':('gcd','Gasoil Dec crack vs Brent','prodspread','$/bbl',4),
 'BRENTM1M2':('b12','Brent Dec/Jan','crudespread','$/bbl',4),'BrentM2M3':('b23','Brent Jan/Feb','crudespread','$/bbl',4),'BrentM1M3':('b13','Brent Dec/Feb','crudespread','$/bbl',4),
 'WTIM1M2':('w12','WTI Dec/Jan','crudespread','$/bbl',4),'WTIM2M3':('w23','WTI Jan/Feb','crudespread','$/bbl',4),'WTIM1M3':('w13','WTI Dec/Feb','crudespread','$/bbl',4),
 'DubaiM1M2':('d12','Dubai Nov/Dec','crudespread','$/bbl',4),'DubaiM2M3':('d23','Dubai Dec/Jan','crudespread','$/bbl',4),'DubaiM1M3':('d13','Dubai Nov/Jan','crudespread','$/bbl',4),
 'NOvDFL':('dfl1','DFL Nov','dfl','$/bbl',0.5),'dECDFL':('dfl2','DFL Dec','dfl','$/bbl',0.5),
 'BRENT DUBAI nov':('bd1','Brent-Dubai Nov (EFS)','eastwest','$/bbl',None),'Brent Dubai Dec':('bd2','Brent-Dubai Dec (EFS)','eastwest','$/bbl',None)}
wb=openpyxl.load_workbook(SRC,data_only=True,read_only=True)
S={};VOL={}
for sh,(k,lab,grp,unit,L) in META.items():
    rows=[(r[0],float(r[1]),(float(r[2]) if len(r)>2 and isinstance(r[2],(int,float)) else np.nan)) for r in wb[sh].iter_rows(min_row=2,values_only=True) if r and r[0] is not None and isinstance(r[1],(int,float))]
    df=pd.DataFrame(rows,columns=['ts','px','vol']).drop_duplicates('ts',keep='last').set_index('ts').sort_index()
    if L: df.index=df.index+pd.Timedelta(hours=L)
    S[k]=df.px; VOL[k]=df.vol
S['qs1b']=S['qs1']/7.45
S['gcn']=(S['qs1b']-S['co1']).dropna()
S['dmb']=(S['d12']-S['b12']).dropna()
EXTRA={'qs1b':('Gasoil Nov $/bbl (QS1/7.45)','flat','$/bbl',4),'gcn':('Gasoil Nov crack vs Brent Dec (QS1/7.45−CO1)','prodspread','$/bbl',4),
       'dmb':('Dubai Nov/Dec − Brent Dec/Jan','crudespread','$/bbl',4)}
info={v[0]:dict(label=v[1],group=v[2],unit=v[3],bar=v[4],sheet=sh) for sh,v in META.items()}
for k,(lab,grp,unit,L) in EXTRA.items(): info[k]=dict(label=lab,group=grp,unit=unit,bar=L,sheet='derived')
asof=max(s.index[-1] for k,s in S.items() if info[k]['bar'])
day_end=(asof-pd.Timedelta(hours=2)).normalize()+pd.Timedelta(hours=2)   # 02:00 Dubai day boundary
Y0,Y1=day_end-pd.Timedelta(days=1),day_end
while Y0.weekday()>=5: Y0-=pd.Timedelta(days=1)
W0=day_end-pd.Timedelta(days=day_end.weekday())  # Monday 02:00
def asof_v(s,t):
    x=s[s.index<=t]; return float(x.iloc[-1]) if len(x) else None
def interp(s,t):
    if t in s.index: return float(s[t])
    a=s[s.index<t]; b=s[s.index>t]
    if not len(a): return None
    if not len(b) or (b.index[0]-a.index[-1])>pd.Timedelta(hours=8): return float(a.iloc[-1])
    w=(t-a.index[-1])/(b.index[0]-a.index[-1]); return float(a.iloc[-1]+w*(b.iloc[0]-a.iloc[-1]))
moves={}
for k,s in S.items():
    if info[k]['bar'] is None:
        d=s.sort_index(); moves[k]=dict(last=float(d.iloc[-1]),last_ts=str(d.index[-1])[:16],yday=float(d.iloc[-1]-d.iloc[-2]) if len(d)>1 else None,
            wk=float(d.iloc[-1]-asof_v(d,W0-pd.Timedelta(hours=26))) if asof_v(d,W0-pd.Timedelta(hours=26)) is not None else None); continue
    y0,y1,w0,l=asof_v(s,Y0),asof_v(s,Y1),asof_v(s,W0),float(s.iloc[-1])
    b=[interp(s,Y0+pd.Timedelta(hours=h)) for h in (0,8,16,24)]
    moves[k]=dict(last=l,last_ts=str(s.index[-1])[:16],y0=y0,y1=y1,yday=None if None in (y0,y1) else y1-y0,today=None if y1 is None else l-y1,
        wk=None if w0 is None else l-w0,sess=None if None in b else dict(Asia=b[1]-b[0],Europe=b[2]-b[1],US=b[3]-b[2]),
        hi_wk=float(s[s.index>=W0].max()),lo_wk=float(s[s.index>=W0].min()))
# lead-lag vs CO1 4h changes, as-of sampling on the CO1 close grid, no interpolation
co=S['co1']; grid=co.index
def chg_at(s,ts,o):
    out=[]
    for t in ts:
        a,b=t-pd.Timedelta(hours=4)+pd.Timedelta(hours=o),t+pd.Timedelta(hours=o)
        xa=s[s.index<=a]; xb=s[s.index<=b]
        ok=len(xa) and len(xb) and (b-xb.index[-1])<pd.Timedelta(hours=2.5) and (a-xa.index[-1])<pd.Timedelta(hours=2.5)
        out.append(float(xb.iloc[-1]-xa.iloc[-1]) if ok else np.nan)
    return np.array(out)
base=[t for t in grid[1:] if (t-grid[grid.get_loc(t)-1])==pd.Timedelta(hours=4)]
dco=np.array([float(co[t]-co[t-pd.Timedelta(hours=4)]) for t in base])
LL={}
for k in ['qs1b','gcn','gcd','g12','b12','b13','w12','w13','d12','d13','dmb','dfl1','dfl2']:
    s=S[k]; offs=sorted({o for o in range(-12,13,2)} if info[k]['bar']==0.5 else ({o for o in range(-12,13,4)} if k in ('qs1b','gcn','g12','b12','b13','d12','d13','dmb') else {o for o in range(-10,11,4)}))
    row={}
    for o in offs:
        x=chg_at(s,base,o); m=~np.isnan(x)
        if m.sum()<25: continue
        r=float(np.corrcoef(dco[m],x[m])[0,1]); beta=float(np.polyfit(dco[m],x[m],1)[0])
        row[str(o)]=dict(r=round(r,3),beta=round(beta,4),n=int(m.sum()))
    best=max(row,key=lambda z:abs(row[z]['r']))
    LL[k]=dict(lags=row,best=int(best))
# 4h-change correlation matrix on the common CO1 grid (same-grid instruments), lag 0
ck=['co1','qs1b','gcn','g12','b12','b13','d12','d13','dmb','dfl1','dfl2']
M=pd.DataFrame({k:chg_at(S[k],base,0) for k in ck}).corr(min_periods=25).round(2)
# daily closes (London 19:30 Dubai) for the DFL vs Brent-Dubai chart
days=sorted({t.normalize() for t in S['dfl1'].index if t.weekday()<5})
dfl_daily={k:[[str(d.date()),asof_v(S[k],d+pd.Timedelta(hours=19,minutes=30))] for d in days] for k in ('dfl1','dfl2')}
ser={k:[[str(t)[:16],round(float(v),4)] for t,v in s.items()] for k,s in S.items()}
out=dict(asof=str(asof)[:16],tz='Dubai (UTC+4), bar close times',yday_start=str(Y0)[:16],yday_end=str(Y1)[:16],week_start=str(W0)[:16],
    info=info,moves=moves,leadlag=LL,corr=dict(keys=ck,m=[[None if pd.isna(M.loc[a,b]) else float(M.loc[a,b]) for b in ck] for a in ck],nbars=len(base)),
    dfl_daily=dfl_daily,series=ser,source_file=SRC.split('/')[-1])
json.dump(out,open(OUT,'w'))
print(out['asof'],out['yday_start'],out['yday_end'],out['week_start'],'bars',len(base))
for k,m in moves.items():
    f=lambda v:'  -   ' if v is None else f"{v:+6.2f}"
    print(f"{k:5} last {m['last']:9.2f} yday {f(m.get('yday'))} today {f(m.get('today'))} wk {f(m.get('wk'))} sess "+(' '.join(f"{a[:2]}{v:+.2f}" for a,v in m['sess'].items()) if m.get('sess') else ''))
for k,v in LL.items(): print(k,'best',v['best'],' '.join(f"{o}:{x['r']:+.2f}/{x['beta']:+.3f}" for o,x in v['lags'].items()))
print(M)
