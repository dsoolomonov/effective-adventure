import json
from datetime import datetime, timedelta, date
p=json.load(open('/home/ubuntu/outg/parsed_new.json'))
rows=[dict(r) for r in p['rows'] if not r.get('start_derived')]
fix=[('crude','unplanned','Asia','CHINA HAIYOU - RIZHAO/SUNRISE','2028-04-20',1215,70.0),
('crude','unplanned','Latin America','BRAZIL REMAN/ISSAC SABBA/MANAUS','2026-12-31',851,31.0),
('fcc','unplanned','Asia','CHINA HAIYOU - RIZHAO/SUNRISE','2028-04-20',1215,12.0),
('fcc','unplanned','Rest of World','IRAN (ISLAMIC REP.) BANDAR ABBAS - HORMOZGAN','2026-11-15',214,5.0),
('fcc','unplanned','Rest of World','IRAN (ISLAMIC REP.) BANDAR ABBAS - HORMOZGAN','2026-11-15',214,45.0),
('coking','unplanned','Asia','CHINA HAIYOU - RIZHAO/SUNRISE','2028-01-20',1124,11.0),
('coking','unplanned','Latin America','VENEZUELA PETROMONAGAS / CERRO NEGRO','2026-12-31',1465,36.0)]
for u,k,r,cr,e,dd,kb in fix:
    s=(datetime.strptime(e,'%Y-%m-%d')-timedelta(days=dd)).strftime('%Y-%m-%d')
    rows.append({'unit':u,'kind':k,'region':r,'country_ref':cr,'start':s,'end':e,'days':dd,'kbd':kb,'type':'UNPLANNED','start_derived':True})
countries=['IRAN (ISLAMIC REP.)','SOUTH KOREA','SAUDI ARABIA','UNITED STATES','RUSSIAN FEDERATION','NETHERLANDS ANTILLES','SOUTH AFRICA','UNITED ARAB EMIRATES','NEW ZEALAND','IVORY COAST','TRINIDAD AND TOBAGO']
RUFIX={'FEDERATIOORNSK':'ORSK','FEDERATIMOONSCOW OIL REFINERY':'MOSCOW OIL REFINERY','FEDERATITOUNAPSE':'TUAPSE','FEDERATIOORNSK':'ORSK','FEDERATISOANLAVAT':'SALAVAT'}
for r in rows:
    for k,v in RUFIX.items(): r['country_ref']=r['country_ref'].replace('RUSSIAN '+k,'RUSSIAN FEDERATION '+v)
    cr=r.pop('country_ref'); c=next((x for x in countries if cr.startswith(x)),cr.split(' ')[0])
    r['country']=c; r['refinery']=cr[len(c):].strip()
seen=set()
for r in rows:
    key=(r['unit'],r['country'],r['refinery'],r['start'],r['end'],r['kbd'],r['type'])
    r['dup']=key in seen; seen.add(key)
months=['2026-11','2026-12','2027-01','2027-02','2027-03','2027-04']
def active(r,m):
    y,mm=map(int,m.split('-')); a=date(y,mm,1); b=date(y+mm//12,mm%12+1,1)-timedelta(days=1)
    s=date.fromisoformat(r['start']); e=date.fromisoformat(r['end'])
    return max(0,(min(b,e)-max(a,s)).days+1)/((b-a).days+1)
listed={u:{k:[round(sum(r['kbd']*active(r,m) for r in rows if r['unit']==u and r['kind']==k and not r['dup'])) for m in months] for k in ('planned','unplanned')} for u in ('crude','fcc','coking')}
print(listed, sum(r['dup'] for r in rows), len(rows))
CAVEATS=['Booked outages are refinery-specific; the hatched forecast cap on top is not attributed to any refinery or country, and is absent where bookings already exceed the forecast.',
"The global key-outages-by-country chart excludes China from the forecast cap, so that cap is lower than the full forecast by China's share.",
'Shaded bands / whiskers are rough ranges, not 80% intervals: they cover the outcome only ~64-77% of the time.',
'PADD 1 & 3 is a subset of United States: never add the two. Booked figures nest exactly; forecasts are fitted separately and may not reconcile.',
'Total = planned & economic + unplanned. The appendix lists key refinery outages only, so listed-capacity sums are not the full pack totals.',
'7 appendix rows had overlapping text in the PDF; their start dates are derived from end date minus duration and names cleaned by hand (marked †).']
NOTE=json.load(open('/home/ubuntu/outg/note.json'))
pack={'report_date':'2026-11-02','prior_date':'2026-10-22','months':['Nov 26','Dec 26','Jan 27','Feb 27','Mar 27','Apr 27'],
'charts':p['charts'],'rows':rows,'listed_avg_kbd':listed,
'revision':{'crude':{'total':[936,105,35,-42,200,189],'by_region_total':[1304,195,-14,-84,286,343]},
            'fcc':{'total':[316,-7,-28,-34,126,20],'by_region_total':[400,40,-15,-18,35,51]},
            'coking':{'total':[167,24,30,-65,-20,0],'by_region_total':[207,24,16,-77,-20,0]}},
'revision_split_note':'Revision totals transcribed from the pack bar labels (new − prior, KBD). Net (planned + unplanned) and by-region totals are separate charts in the pack and do not reconcile (crude Nov +936 net vs +1,304 by region); treat both as approximate.',
'm0':'Nov 2026',
'crude_country_oct':{'planned':{'Venezuela':633,'China':567,'Mexico':494,'Iran':382,'India':336,'United States':330,'Japan':327,'Kuwait':219,'South Korea':118},
                     'unplanned':{'Saudi Arabia':859,'Russia':517,'Ukraine':498,'Nigeria':235,'China':234,'Libya':220,'Yemen':100,'Jordan':72,'Kuwait':60,'Iran':60,'Pakistan':60}},
'crude_seasonal_total':{'note':'Read off the global crude total seasonal chart (approx., KBD)',
 '2025':[9200,11000,11200,13100,13900,11200,8800,9200,11500,13100,12200,8700],
 '2026_all':[8000,8800,12300,16000,15800,14700,14500,12500,15200,12800,9400,6000],
 '2026_forecast':[None]*9+[12800,10600,9300],
 '2027_booked':[5300,5500,6100,7500,6900,4800,3600,2300,2500,3200,2800,1600],
 '2027_forecast':[9800,11200,11800,14000,13200,11700,10400,9500,11200,12100,9800,7000]},
'note':NOTE,
'caveats':CAVEATS}
json.dump(pack,open('/home/ubuntu/crude-oil-analytics/app/outages.json','w'),separators=(',',':'))
