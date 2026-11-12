exec(open('probe.py').read().split("SY=")[0])
import sys,time,json; sys.path.insert(0,'/home/ubuntu/crude-oil-analytics')
from app import crude_diffs_live as m
t=time.time(); p=m.build_payload(get); print('secs',round(time.time()-t,1),'as_of',p['as_of'],'bytes',len(json.dumps(p)))
for g in p['groups']:
    print('##',g['short'])
    for x in g['grades']:
        s=x['stats']; f=lambda k:('%+.2f'%s[k]) if s.get(k) is not None else '  —'
        print(f"{x['name']:15}{s['status']:6}{s.get('date')} {s.get('value'):7.2f} dd{f('dod')} ww{f('wow')} mm{f('mom')} yy{f('yoy')} 5y{f('vs5y')}({s['five_n']}) pct{s['pctile5y']} hi{s['hi52']}@{s['hi52_date']} lo{s['lo52']}")
json.dump(p,open('cd.json','w'))
