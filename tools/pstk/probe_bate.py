exec(open('probe.py').read().split("SY=")[0])
import time
t=time.time()
j=get("/market-data/v3/value/history/symbol",{"filter":'symbol IN ("AAGWZ00","AAGXB00") AND bate:"c" AND assessDate>="2021-01-01"',"pageSize":10000})
print(time.time()-t, j.get('metadata'), [(r['symbol'],len(r['data']),set(x['bate'] for x in r['data'])) for r in j['results']])
