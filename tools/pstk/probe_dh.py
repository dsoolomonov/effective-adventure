exec(open('probe.py').read().split("SY=")[0])
S="AAGWZ00 AAGXB00 AAGXF00 AJSVB00 AAGXD00 WMCRB00 AAWEY00 PCALB00 AAVJB00 AAGXH00 AAHPL00 AAHPM00 AAUFJ00 AAHPN00 AAGYH00 AAGYF00 AAGXJ00 AAHPK00 AALVZ00 AAGYD00 KBCOB00 AAHXB00 AAHXD00".split()
for s in S:
    try:
        j=get("/market-data/v3/value/history/symbol",{"filter":f'symbol IN ("{s}") AND assessDate>="2016-01-01"',"pageSize":10000})
        d=[(x['assessDate'][:10],x['value'],x.get('bate')) for r in j.get('results',[]) for x in r.get('data',[])]
        d.sort()
        print(s,len(d),d[0] if d else None,d[-3:] if d else None)
    except Exception as e: print(s,'ERR',str(e)[:150])
