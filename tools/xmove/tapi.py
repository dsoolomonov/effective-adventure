import re,sys,time,json,urllib.request as ur,urllib.parse as up,http.cookiejar as cj
base=sys.argv[1]
env=dict(x.split(b'=',1) for x in open('/home/ubuntu/xmove/.env.run','rb').read().split(b'\0') if b'=' in x)
pw=(env.get(b'APP_PASSWORD',b'').decode() if '127.0.0.1' in sys.argv[1] else '') or re.search(r'_APP_PASSWORD = os.environ.get\("APP_PASSWORD", "([^"]*)"\)',open('/home/ubuntu/crude-oil-analytics/app/main.py').read()).group(1)
op=ur.build_opener(ur.HTTPCookieProcessor(cj.CookieJar()))
try: r=op.open(base+'/auth/login',data=up.urlencode({'password':pw}).encode()); print('login',r.status)
except Exception as e: print('login err',e)
t=time.time(); r=op.open(base+'/api/ea'+(sys.argv[2] if len(sys.argv)>2 else '')); b=json.loads(r.read()); print('status',r.status,'secs',round(time.time()-t,1),'bytes',len(json.dumps(b)))
print('latest',b.get('latest_release'),'n',len(b.get('series',{})),'err',b.get('error'),b.get('errors'))
