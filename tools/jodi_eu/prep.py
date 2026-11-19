import pandas as pd
g=pd.read_csv('/home/ubuntu/jodi_chk/NewProcedure_Secondary_CSV.csv',dtype=str)
g['OBS_VALUE']=pd.to_numeric(g.OBS_VALUE,errors='coerce')
g=g.dropna(subset=['OBS_VALUE'])
g=g[g.ENERGY_PRODUCT.isin(['GASOLINE','GASDIES'])]
g=g[((g.FLOW_BREAKDOWN.isin(['REFGROUT','TOTDEMO','TOTIMPSB','TOTEXPSB']))&(g.UNIT_MEASURE=='KBD'))|((g.FLOW_BREAKDOWN=='CLOSTLV')&(g.UNIT_MEASURE=='KBBL'))]
g.to_parquet('sec.parquet')
print(g.TIME_PERIOD.max(), len(g))
