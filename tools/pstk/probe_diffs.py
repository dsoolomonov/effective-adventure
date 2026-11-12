exec(open('probe.py').read().split("SY=")[0])
import re
qs=['FOB North Sea vs North Sea Dtd Strip','Forties FOB North Sea vs','Ekofisk FOB North Sea vs','Oseberg FOB North Sea vs','Statfjord FOB North Sea vs','Troll FOB North Sea vs','vs Med Dtd Strip','Azeri Light CIF Augusta','Azeri BTC FOB Ceyhan','BTC Dated Strip','Saharan Blend FOB','Es Sider FOB','CPC Blend FOB','CPC Blend CIF Augusta','Urals Med','Kirkuk FOB Ceyhan','Siberian Light','WTI Midland FOB','Midland CIF Augusta','Forties diff','Brent FOB diff']
for q in qs:
    out=[]
    for pg in (1,2):
        try: j=get("/market-data/reference-data/v3/search",{"q":q,"pageSize":50,"page":pg})
        except Exception as e: print(q,e); break
        out+= [(x.get('symbol'),x.get('description'),x.get('assessment_frequency') or x.get('frequency'),x.get('uom')) for x in j.get('results',[])]
    out=[o for o in out if re.search(r'strip|diff|vs',o[1] or '',re.I)]
    print('##',q); [print('  ',*o) for o in out[:25]]
