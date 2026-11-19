exec(open('probe.py').read().split("SY=")[0])
import concurrent.futures as cf
SY="AALHA00 AALHC00 AALQT00 AALHB00 AALHI00 AALHG00 AALHH00 AALSC00 AALOH00 AALOI00 AALOJ00 AALOM00 AALOC00 AALOL00 AAVQY00 EIAIC00 EIAIG00 EIAIH00 EIAII00 EIAIJ00 EIALY00 EIAMC00 EIAMD00 EIAME00 EIAMF00 EIALZ00 EIAMA00 EIAMB00 EIALS00 EIALT00 EIALU00 EIALV00 EIALW00 EIANI00 EIANM00 EIANN00 EIANO00 EIANP00 EIAWB00 EIAWC00 EIAWE00 EIAWF00 EIAWI00 EIAHW00 EIABQ00 EIAIA00".split()
def h(s):
    j=get("/market-data/v3/value/history/symbol",{"filter":f'symbol: "{s}" AND assessDate >= "2016-06-01"',"pageSize":10000})
    r=j.get('results',[])
    if not r: return s,'none'
    d=sorted(r[0]['data'],key=lambda x:x['assessDate'])
    return s,(len(d),d[0]['assessDate'][:10],[(x['assessDate'][:10],x['value']) for x in d[-2:]])
with cf.ThreadPoolExecutor(8) as ex:
    for s,v in ex.map(h,SY): print(s,v)
