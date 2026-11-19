exec(open('probe.py').read().split("SY=")[0])
import re
qs=['PAJ Gasoline','PAJ Kero','PAJ Gasoil','PAJ Naphtha','PAJ Jet','PAJ FO','PAJ Prod Stks','PAJ Unfinish','PAJ Tot','EIA 9 MoGas PADD','EIA 9 Dist FO PADD','EIA 9 Resid FO PADD','EIA 9 Crude Comml PADD','EIA 9 Jet PADD1 Stks','EIA 1 Crude in SPR','EIA 9 Crude SPR','EIA 9 MoGas PADD1A','EIA 9 Dist FO PADD1A']
seen={}
for q in qs:
    out=[]
    for pg in (1,2):
        j=get("/market-data/reference-data/v3/search",{"q":q,"pageSize":50,"page":pg})
        out+= [(x.get('symbol'),x.get('description')) for x in j.get('results',[])]
    out=[o for o in out if re.search(r'Stk|Stock',o[1] or '',re.I)]
    print('##',q); [print('  ',s,d) for s,d in out[:40]]
