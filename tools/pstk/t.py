import sys,json,time
sys.path.insert(0,'/home/ubuntu/crude-oil-analytics')
exec(open('/home/ubuntu/pstk/probe.py').read().split("SY=")[0])
from app import product_stocks_live as L
t=time.time(); p=L.build_payload(get); print('payload s',round(time.time()-t,1))
json.dump(p,open('/home/ubuntu/pstk/payload.json','w'))
G=[g for g,_ in L.GROUPS]
for r in p['summary']['rows']:
    line=f"{r['name']:<10}"
    for g in G:
        c=r['cells'].get(g)
        if not c: line+=' '*30; continue
        if c['status']!='ok': line+=f"{c['status']:<30}"; continue
        f=lambda v: '  —  ' if v is None else f"{v:6.1f}"
        line+=f"{f(c['value'])}{f(c['wow'])}{f(c['yoy'])}{f(c['vs1719'])}  "
    print(line)
for rg in p['regions']: print(rg['name'],rg['stale'],rg['unavailable'])
t=time.time(); n=L.build_news(get); print('news s',round(time.time()-t,1))
for a in n['articles']: print(a['updated'],a['headline'],'|',(a['lead'] or '')[:100])
