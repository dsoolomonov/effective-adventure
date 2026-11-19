from load import *
d=load()
def bars(k):
    df=d[k].copy(); df['gap']=df.index.to_series().diff().dt.total_seconds()/3600; df['chg']=df.px.diff()
    df['sess']=[('Wknd gap' if g>12 else session(t.hour)) for t,g in zip(df.index,df.gap)]
    return df.iloc[1:]
for k in ['B12','DFL1','G12','HG1','GC1','RC1','BD1','D12','W12']:
    b=bars(k); print(k,{s:round(b[b.sess==s].chg.sum(),2) for s in ['Asia','Europe','US','Wknd gap']})
    top=b.reindex(b.chg.abs().sort_values(ascending=False).index).head(4)
    print('  top bars',[(str(t)[5:13],s,round(c,2)) for t,s,c in zip(top.index,top.sess,top.chg)])
# per Dubai-day session table for B12 last 10 days
b=bars('B12'); b['day']=b.index.date
print(b.pivot_table(index='day',columns='sess',values='chg',aggfunc='sum').round(2).tail(10))
