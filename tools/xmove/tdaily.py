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
import sys; sys.path.insert(0,'/home/ubuntu/crude-oil-analytics')
from app import cross_moves_live as m
import time; t=time.time(); p=m.build_payload(get); print('secs',round(time.time()-t,1),p['as_of'])
json.dump(p,open('daily.json','w'))
S=p['stats']
for k in ['dated','brent1','wti','dubai','oman','murban','bd','bwti','wtidub','dfl','murdub','go_bbl','ulsd_bbl','jet_bbl','ebob_bbl','nap_bbl','fo35_bbl','sgo_bbl','s92_bbl','s380_bbl','go_crk','ulsd_crk','jet_crk','ebob_crk','nap_crk','fo35_crk','sgo_crk','s92_crk','s380_crk']:
    s=S[k]; f=lambda v:'   -  ' if v is None else f"{v:+6.2f}"
    print(f"{p['names'][k][:34]:35}{s['date']} {s['value']:8.2f} dd{f(s['dod'])} ww{f(s['wow'])} mm{f(s['mom'])}")
print('lags vs Dated, 60d | 250d  (lag L: product change on day t+L vs Dated on t)')
for k,v in p['lags'].items():
    print(f"{k:10}"+' '.join(f"{L}:{v['60'][L]['r'] if v['60'][L]['r'] is not None else 'na'}" for L in v['60'])+' | '+' '.join(f"{L}:{v['250'][L]['r']}" for L in v['250'])+f"  b0={v['60']['0']['beta']}")
print('roll BD-DFL', p['bd_dfl_roll60'][-1], p['bd_dfl_roll60'][-120][0], p['bd_dfl_roll60'][-120][1])
