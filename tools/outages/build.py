import json
from datetime import datetime, timedelta, date
p=json.load(open('parsed.json'))
rows=[dict(r) for r in p['rows'] if not r.get('start_derived')]
fix=[('crude','unplanned','Asia','CHINA HAIYOU - RIZHAO/SUNRISE','2028-04-20',1215,70.0),
('crude','unplanned','Latin America','BRAZIL REMAN/ISSAC SABBA/MANAUS','2026-12-31',851,31.0),
('fcc','unplanned','Asia','CHINA HAIYOU - RIZHAO/SUNRISE','2028-04-20',1215,12.0),
('fcc','unplanned','Rest of World','IRAN (ISLAMIC REP.) BANDAR ABBAS - HORMOZGAN','2026-11-15',215,5.0),
('fcc','unplanned','Rest of World','IRAN (ISLAMIC REP.) BANDAR ABBAS - HORMOZGAN','2026-11-15',215,45.0),
('coking','unplanned','Asia','CHINA HAIYOU - RIZHAO/SUNRISE','2028-01-20',1124,11.0),
('coking','unplanned','Latin America','VENEZUELA PETROMONAGAS / CERRO NEGRO','2026-12-31',1465,36.0),
('coking','unplanned','Latin America','VENEZUELA PETROPIAR / HAMACA','2026-10-15',35,15.0)]
for u,k,r,cr,e,dd,kb in fix:
    s=(datetime.strptime(e,'%Y-%m-%d')-timedelta(days=dd)).strftime('%Y-%m-%d')
    rows.append({'unit':u,'kind':k,'region':r,'country_ref':cr,'start':s,'end':e,'days':dd,'kbd':kb,'type':'UNPLANNED','start_derived':True})
countries=['IRAN (ISLAMIC REP.)','SOUTH KOREA','SAUDI ARABIA','UNITED STATES','RUSSIAN FEDERATION','NETHERLANDS ANTILLES','SOUTH AFRICA','UNITED ARAB EMIRATES','NEW ZEALAND','IVORY COAST','TRINIDAD AND TOBAGO']
RUFIX={'FEDERATIMOONSCOW OIL REFINERY':'MOSCOW OIL REFINERY','FEDERATITOUNAPSE':'TUAPSE','FEDERATIOORNSK':'ORSK','FEDERATISOANLAVAT':'SALAVAT'}
for r in rows:
    for k,v in RUFIX.items(): r['country_ref']=r['country_ref'].replace('RUSSIAN '+k,'RUSSIAN FEDERATION '+v)
    cr=r.pop('country_ref'); c=next((x for x in countries if cr.startswith(x)),cr.split(' ')[0])
    r['country']=c; r['refinery']=cr[len(c):].strip()
seen=set()
for r in rows:
    key=(r['unit'],r['country'],r['refinery'],r['start'],r['end'],r['kbd'],r['type'])
    r['dup']=key in seen; seen.add(key)
months=['2026-10','2026-11','2026-12','2027-01','2027-02','2027-03']
def active(r,m):
    y,mm=map(int,m.split('-')); a=date(y,mm,1); b=date(y+mm//12,mm%12+1,1)-timedelta(days=1)
    s=date.fromisoformat(r['start']); e=date.fromisoformat(r['end'])
    return max(0,(min(b,e)-max(a,s)).days+1)/((b-a).days+1)
listed={u:{k:[round(sum(r['kbd']*active(r,m) for r in rows if r['unit']==u and r['kind']==k and not r['dup'])) for m in months] for k in ('planned','unplanned')} for u in ('crude','fcc','coking')}
print(listed, sum(r['dup'] for r in rows), len(rows))
pack={'report_date':'2026-10-08','prior_date':'2026-09-25','months':['Oct 26','Nov 26','Dec 26','Jan 27','Feb 27','Mar 27'],
'charts':p['charts'],'rows':rows,'listed_avg_kbd':listed,
'revision':{'crude':{'total':[884,-110,-417,128,-230,-22],'by_region_total':[882,157,-384,241,None,12]},
            'fcc':{'total':[247,24,140,168,-41,102]},'coking':{'total':[259,48,83,123,44,59]}},
'revision_split_note':'Revision totals transcribed from the pack bar labels (new − prior, KBD). Crude net vs by-region totals differ after Oct (Nov −110 vs +157, Jan +128 vs +241); the pack does not reconcile them, so treat the by-region split as indicative.',
'crude_country_oct':{'planned':{'United States':994,'China':769,'Venezuela':753,'Mexico':496,'Japan':433,'Saudi Arabia':400,'Iran':395,'South Korea':339,'Ukraine':300,'Netherlands Antilles':242,'India':176},
                     'unplanned':{'Russia':970,'Ukraine':498,'Saudi Arabia':383,'China':263,'Kuwait':263,'Nigeria':235,'Libya':220,'Iran':192,'Yemen':130,'Pakistan':60}},
'crude_seasonal_total':{'note':'Read off the global crude total seasonal chart (approx., KBD)','2026_all':[7950,8700,12200,15950,15650,14600,14350,12400,15100,11100,7350,5600],'2026_forecast':[None]*9+[11350,9200,6950],'2025':[9150,10950,11150,13000,13800,11100,8750,9250,11450,12600,12150,8600],'2027_booked':[5500,5600,5900,7000,6700,4800,3800,2350,2550,3250,2800,1600]},
'caveats':['Booked outages are refinery-specific; the hatched forecast cap on top is not attributed to any refinery or country, and is absent where bookings already exceed the forecast.',
"The global key-outages-by-country chart excludes China from the forecast cap, so that cap is lower than the full forecast by China's share.",
'Shaded bands / whiskers are rough ranges, not 80% intervals: they cover the outcome only ~64-77% of the time.',
'PADD 1 & 3 is a subset of United States: never add the two. Booked figures nest exactly; forecasts are fitted separately and may not reconcile.',
'Total = planned & economic + unplanned. The appendix lists key refinery outages only, so listed-capacity sums are not the full pack totals.',
'8 appendix rows had overlapping text in the PDF; their start dates are derived from end date minus duration and names cleaned by hand (marked †).']}
json.dump(pack,open('/home/ubuntu/crude-oil-analytics/app/outages.json','w'),separators=(',',':'))
