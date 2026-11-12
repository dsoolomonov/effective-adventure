import os, requests, json, concurrent.futures as cf, pandas as pd
K=os.environ['EIA_API_KEY']
S={
'gas_stk':'WGTSTUS1','gas_fin_stk':'WGFSTUS1','gas_blend_stk':'WBCSTUS1',
'gas_stk_p1':'WGTSTP11','gas_stk_p2':'WGTSTP21','gas_stk_p3':'WGTSTP31','gas_stk_p4':'WGTSTP41','gas_stk_p5':'WGTSTP51',
'gas_stk_p1a':'WGTST1A1','gas_stk_p1b':'WGTST1B1','gas_stk_p1c':'WGTST1C1',
'gas_dem':'WGFUPUS2','gas_prod':'WGFRPUS2','gas_imp':'WGTIMUS2','gas_exp':'W_EPM0F_EEX_NUS-Z00_MBBLD','gas_blend_imp':'WBCIMUS2',
'dist_stk':'WDISTUS1','dist_stk_p1':'WDISTP11','dist_stk_p2':'WDISTP21','dist_stk_p3':'WDISTP31','dist_stk_p4':'WDISTP41','dist_stk_p5':'WDISTP51',
'dist_stk_p1a':'WDIST1A1','dist_stk_p1b':'WDIST1B1','dist_stk_p1c':'WDIST1C1',
'ulsd_stk':'WD0ST_NUS_1','dist_dem':'WDIUPUS2','dist_prod':'WDIRPUS2','dist_imp':'WDIIMUS2','dist_exp':'WDIEXUS2',
'util':'WPULEUS3','crude_runs':'WCRRIUS2','gross_in':'WGIRIUS2',
'util_p1':'W_NA_YUP_R10_PER','util_p2':'W_NA_YUP_R20_PER','util_p3':'W_NA_YUP_R30_PER','util_p4':'W_NA_YUP_R40_PER','util_p5':'W_NA_YUP_R50_PER',
'crude_stk':'WCESTUS1','cushing':'W_EPC0_SAX_YCUOK_MBBL','spr':'WCSSTUS1','crude_prod':'WCRFPUS2','crude_imp':'WCEIMUS2','crude_exp':'WCREXUS2',
'jet_stk':'WKJSTUS1','jet_dem':'WKJUPUS2','tot_dem':'WRPUPUS2','prop_stk':'WPRSTUS1','resid_stk':'WRESTUS1',
'ethanol_prod':'W_EPOOXE_YOP_NUS_MBBLD','ethanol_stk':'W_EPOOXE_SAE_NUS_MBBL',
}
def get(item):
    k,sid=item
    try:
        r=requests.get(f'https://api.eia.gov/v2/seriesid/PET.{sid}.W',params={'api_key':K,'start':'2019-01-01','length':5000},timeout=60)
        d=r.json()['response']['data']
        return k,{x['period']:float(x['value']) for x in d if x.get('value') not in (None,'')}
    except Exception as e:
        return k,str(e)[:100]
out={}
with cf.ThreadPoolExecutor(12) as ex:
    for k,v in ex.map(get,S.items()):
        if isinstance(v,dict) and v: out[k]=v
        else: print('FAIL',k,v)
df=pd.DataFrame(out).sort_index(); df.index=pd.to_datetime(df.index)
df.to_pickle('wk.pkl'); print(df.index.max(), df.shape); print(df.tail(3).T.to_string())
