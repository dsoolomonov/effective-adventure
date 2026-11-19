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
SY={'PCAAS00':'Dated Brent','PCAAQ00':'Brent Mo01','PCAAT00':'Dubai Mo01','PCACG00':'WTI Cushing Mo01','AAKNL00':'Murban Mo01','PCABS00':'Oman Mo01',
'AAJMS00':'Brent Mo01 vs Dubai Mo01 Spore','DBVBM00':'Dated vs Brent Mo01','AARBZ00':'Murban vs Dubai','AALAU00':'Brent Mo01 vs WTI Mo01','ICLL001':'ICE Brent settle Mo01','ICLO001':'ICE Gasoil settle Mo01',
'AAYWS00':'Gasoil 0.1 CIF NWE','AAVBG00':'ULSD 10ppm CIF NWE','AAQZV00':'Eurobob FOB AR','PJAAU00':'Jet CIF NWE','PAAAL00':'Naphtha CIF NWE','PUABC00':'FO 3.5 FOB Rdam',
'AAOVC00':'Gasoil 10ppm FOB Spore','PGAEY00':'Gasoline 92 FOB Spore','PPXDK00':'FO 380 FOB Spore','AAGJA00':'Gasoline 92 FOB AG','PCAAA00':'?','PCAAO00':'?'}
def h(s):
    out={};pg=1
    while True:
        j=get("/market-data/v3/value/history/symbol",{"filter":f'symbol: "{s}" AND assessDate >= "2024-01-01"',"pageSize":10000,"page":pg})
        if 'err' in j: return s,j
        for r in j.get('results',[]):
            for d in r['data']:
                if d.get('value') is not None: out.setdefault(d['bate'],{})[d['assessDate'][:10]]=float(d['value'])
        if pg>=int((j.get('metadata') or {}).get('totalPages') or 1): return s,out
        pg+=1
res={}
with cf.ThreadPoolExecutor(8) as ex:
    for s,v in ex.map(h,SY):
        res[s]=v
        if isinstance(v,dict) and 'err' not in v: print(s,SY[s],{b:(len(x),max(x),x[max(x)]) for b,x in v.items()})
        else: print(s,v)
json.dump({'names':SY,'data':res},open('platts_daily.json','w'))
