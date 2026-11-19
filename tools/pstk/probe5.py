exec(open('probe.py').read().split("SY=")[0])
import re
for q in ['stocks','inventories','stockpiles','Fujairah stocks','ARA stocks','Insights Global','Enterprise Singapore','EIA inventories','PAJ']:
    j=get("/news-insights/v1/search",{"q":q,"pageSize":30,"sort":"updatedDate:desc"})
    hs=[(x.get('updatedDate','')[:16],x.get('headline') or x.get('title')) for x in j.get('results',[])]
    print('##',q); [print('  ',a,b) for a,b in hs if re.search(r'stock|inventor|stockpile',b or '',re.I)][:12]
