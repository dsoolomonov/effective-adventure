import json,collections as C
r=[x for x in json.load(open('fx14.json')) if x['FixtureStatus']!='Failed']
ASIA={'North China':'China','Central China':'China','South China':'China','Singapore / Malaysia':'Sing/Malaysia','Pakistan / West Coast India':'India/Pak','East Coast India':'India/Pak','Korea':'Korea','Japan Island':'Japan','Thailand / Vietnam':'SE Asia other','Taiwan':'Taiwan','Indonesia':'SE Asia other'}
def win(a,b): return [x for x in r if a<=x['FixtureDate'][:10]<=b]
def mb(xs): return sum((x['QuantityInBarrels'] or 0) for x in xs)/1e6
for name,(a,b) in {'last3 16-19Oct':('2026-10-16','2026-10-19'),'last7 12-19Oct':('2026-10-12','2026-10-19'),'prior7 05-11Oct':('2026-10-05','2026-10-11')}.items():
  for grp in ['Dirty','Clean']:
    w=[x for x in win(a,b) if x['CargoGroup']==grp]
    known=[x for x in w if x['LastDischargePortLevel0AreaName']]
    asia=[x for x in known if x['LastDischargePortLevel0AreaName'] in ASIA]
    print(f"\n== {name} {grp}: n={len(w)} known_dest={len(known)} asia={len(asia)} ({100*len(asia)/max(1,len(known)):.0f}%) vol asia {mb(asia):.1f}mb of {mb(known):.1f}mb ({100*mb(asia)/max(.01,mb(known)):.0f}%)")
    if grp=='Clean': continue
    for cls in ['VLCC','Suezmax','Aframax']:
      k=[x for x in known if x['VesselClass']==cls]; s=[x for x in asia if x['VesselClass']==cls]
      print(f"  {cls}: {len(s)}/{len(k)} ({100*len(s)/max(1,len(k)):.0f}%) {mb(s):.1f}mb/{mb(k):.1f}mb")
    print('  dest:',C.Counter(ASIA[x['LastDischargePortLevel0AreaName']] for x in asia).most_common(), {k:round(mb([x for x in asia if ASIA[x['LastDischargePortLevel0AreaName']]==k]),1) for k in set(ASIA.values())})
    print('  load:',C.Counter(x['FirstLoadPortLevel0AreaName'] for x in asia).most_common())
    print('  load mb:',sorted({k:round(mb([x for x in asia if x['FirstLoadPortLevel0AreaName']==k]),1) for k in set(x['FirstLoadPortLevel0AreaName'] for x in asia)}.items(),key=lambda t:-t[1]))
    print('  status:',C.Counter(x['FixtureStatus'] for x in asia), 'unknown dest',len(w)-len(known))
print("\n== last3 dirty Asia VLCC/Suez list")
for x in sorted(win('2026-10-16','2026-10-19'),key=lambda x:x['FixtureDate']):
  if x['CargoGroup']=='Dirty' and x['LastDischargePortLevel0AreaName'] in ASIA and x['VesselClass']!='Aframax':
    print(x['FixtureDate'][:10],x['VesselClass'][:4],x['VesselName'],x['FixtureStatus'],'COA' if x['FixtureIsCOA'] else '',x['FirstLoadPortName'],'->',x['LastDischargePortName'],x['Charterer'],(x['LaycanFrom'] or '')[:10],x['Rate'],x['RateType'],x['QuantityInBarrels'])
print("\n== last3 dirty non-Asia VLCC")
for x in win('2026-10-16','2026-10-19'):
  if x['CargoGroup']=='Dirty' and x['VesselClass']=='VLCC' and x['LastDischargePortLevel0AreaName'] not in ASIA:
    print(x['FixtureDate'][:10],x['VesselName'],x['FixtureStatus'],x['FirstLoadPortName'],'->',x['LastDischargePortName'],x['Charterer'])
print("\n== last7 AG-loaded dirty by dest region")
w=[x for x in win('2026-10-12','2026-10-19') if x['CargoGroup']=='Dirty' and x['FirstLoadPortLevel0AreaName']=='Arabian Gulf']
print(len(w),C.Counter(x['LastDischargePortLevel0AreaName'] for x in w).most_common())
