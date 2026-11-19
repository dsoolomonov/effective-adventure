import os, requests, pandas as pd
for line in open('/home/ubuntu/barrel-terminal-bundle/FILLED.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1); os.environ.setdefault(k, v.strip().strip('"'))
key = os.environ['EIA_API_KEY']
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200)
# monthly imports by country of origin into PADD1: products finished gasoline EPM0F, blending comps EPOBG
def get(route, params):
    p = {"api_key": key, "frequency": "monthly", "data[0]": "value", "sort[0][column]": "period", "sort[0][direction]": "desc", "length": 5000}
    p.update(params)
    r = requests.get(f"https://api.eia.gov/v2/petroleum/move/{route}/data/", params=p, timeout=90)
    j = r.json()
    if 'response' not in j: print(j); return pd.DataFrame()
    return pd.DataFrame(j['response']['data'])
d = get("impcp", {"facets[product][]": ["EPM0F", "EPOBG", "EPOBGRR"], "start": "2025-01"})
print(len(d), d.columns.tolist() if len(d) else None)
if len(d):
    d = d[d['duoarea'].str.startswith('R10-')]
    d['value'] = pd.to_numeric(d['value'], errors='coerce')
    d['origin'] = d['area-name'] if 'area-name' in d.columns else d['duoarea']
    print(d[['period','duoarea','series-description','value','units']].head(5).to_string())
    # Europe origins
    eu = d[d['series-description'].str.contains('Netherlands|United Kingdom|Belgium|France|Germany|Spain|Italy|Norway|Sweden|Finland|Denmark|Portugal|Lithuania|Latvia|Estonia|Poland|Greece|Ireland|Turkey|Europe', regex=True)]
    eu['country'] = eu['series-description'].str.extract(r'from (.+?) of')[0]
    eu['prod'] = eu['product-name'] if 'product-name' in eu.columns else eu['product']
    pv = eu.pivot_table(index=['period'], columns=['prod','country'], values='value', aggfunc='sum').sort_index(ascending=False)
    print(pv.head(9).to_string())
    tot = eu.groupby(['period','prod'])['value'].sum().unstack().sort_index(ascending=False)
    print("\nEurope total -> PADD1 (kb/d):"); print(tot.head(12).to_string())
    d.to_csv('/home/ubuntu/sig/eia_padd1_imp.csv', index=False)
