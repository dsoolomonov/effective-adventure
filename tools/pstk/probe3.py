exec(open('probe.py').read().split("SY=")[0])
for s in ['AALNX00','AALSB00','ARSTG04','FUJLD04','SSGP199','EIABC00','AAVQZ00']:
    j=get("/market-data/v3/value/history/symbol",{"filter":f'symbol: "{s}" AND assessDate >= "2016-01-01"',"pageSize":10000})
    r=j.get('results',[]); 
    if not r: print(s,'none',str(j)[:200]); continue
    d=sorted(r[0]['data'],key=lambda x:x['assessDate']); print(s,len(d),d[0]['assessDate'][:10],d[-1]['assessDate'][:10], j.get('metadata'))
n=get("/news-insights/v1/search",{"q":"stocks","pageSize":3,"sort":"updatedDate:desc"})
i=n['results'][0]['id']; print(n['results'][0])
for p in [f"/news-insights/v1/content/{i}",f"/news-insights/v1/{i}",f"/news-insights/v1/search/{i}"]:
    j=get(p,{}); print(p,str(j)[:800])
j=get("/news-insights/v1/search",{"q":"stocks","pageSize":2,"sort":"updatedDate:desc","field":"headline"}); print(str(j)[:600])
