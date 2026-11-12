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
QS=['Dated Brent','Dubai Mo01','WTI Cushing','Murban','Oman Mo01','Gasoil 0.1% CIF NWE','ULSD 10ppmS CIF NWE','Eurobob FOB AR','Jet CIF NWE','Naphtha CIF NWE','FO 3.5% FOB Rotterdam','Gasoil 10ppm FOB Singapore','Gasoline 92 RON FOB Singapore','380 CST Singapore','Brent Mo01','DFL']
def s(q):
    j=get("/market-data/reference-data/v3/search",{"q":q,"pageSize":12})
    return q,[(x.get('symbol'),x.get('description'),x.get('frequency'),x.get('uom') or x.get('unitOfMeasure')) for x in j.get('results',[])]
with cf.ThreadPoolExecutor(8) as ex:
    for q,r in ex.map(s,QS):
        print('##',q)
        for x in r: print('   ',x)
