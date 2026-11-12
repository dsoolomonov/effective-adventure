import os,json,urllib.request as ur,urllib.parse as up,concurrent.futures as cf
env={}
for l in open('/home/ubuntu/barrel-terminal-bundle/FILLED.env'):
    if '=' in l and not l.startswith('#'): k,v=l.strip().split('=',1); env[k]=v.strip('"')
B="https://api.platts.com";UA="Mozilla/5.0"
tok=json.loads(ur.urlopen(ur.Request(B+"/auth/api",data=up.urlencode({"username":env['SPGCI_USERNAME'],"password":env['SPGCI_PASSWORD']}).encode(),headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":UA}),timeout=30).read())['access_token']
def get(path,params):
    u=B+path+"?"+up.urlencode(params)
    try: return json.loads(ur.urlopen(ur.Request(u,headers={"Authorization":"Bearer "+tok,"User-Agent":UA,"Accept":"application/json"}),timeout=60).read())
    except ur.HTTPError as e: return {'err':e.code,'d':e.read().decode()[:200]}
SY="ARSTL04 ARSTG04 ARSTN04 ARSTM04 ARSTO04 ARSTJ04 ARSTF04 ARSTR04 SSGP199 SSGP229 SSGP599 AAVQZ00 AALNX00 AALNZ00 AALQU00 AALNY00 AALOF00 AALOE00 AALOD00 AALSB00 FUJLD04 FUJMD04 FUJHD04 EIABC00 EIABH00 EIABG00 EIABL00 EIAWA00".split()
def h(s):
    j=get("/market-data/v3/value/history/symbol",{"filter":f'symbol: "{s}" AND assessDate >= "2026-06-01"',"pageSize":1000})
    if 'err' in j: return s,j
    r=j.get('results',[])
    if not r: return s,'no results'
    d=r[0]['data']; d=sorted(d,key=lambda x:x['assessDate'])
    return s,(r[0].get('symbol'),len(d),[ (x['assessDate'][:10],x['bate'],x['value']) for x in d[-3:]])
with cf.ThreadPoolExecutor(8) as ex:
    for s,v in ex.map(h,SY): print(s,v)
for q in ['PAJ stocks','Crude Stks Wkly','EIA 9 Crude Comml Cushing','EIA 1 Jet Kero','ARA crude stocks','Insights Global crude']:
    j=get("/market-data/reference-data/v3/search",{"q":q,"pageSize":15})
    print('##',q,[(x.get('symbol'),x.get('description'),x.get('frequency')) for x in j.get('results',[])][:15])
n=get("/news-insights/v1/search",{"q":"stocks inventories","pageSize":5,"sort":"updatedDate:desc"})
print(json.dumps(n)[:2500])
