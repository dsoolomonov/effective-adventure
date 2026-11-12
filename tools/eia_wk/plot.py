import pandas as pd, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
df=pd.read_pickle('wk_full.pkl'); T=df.index.max()
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
C26,C25='#c0392b','#2c3e50'
def seas(ax,s,title,unit):
    s=s.dropna(); w=s.index.isocalendar().week.clip(upper=52).values; y=s.index.year
    d=pd.DataFrame({'v':s.values,'w':w,'y':y}).groupby(['y','w']).v.mean().unstack(0)
    h=d[[c for c in range(2021,2026) if c in d]]
    x=h.index
    ax.fill_between(x,h.min(1),h.max(1),color='#bdc3c7',alpha=.6,label='2021-25 range')
    ax.plot(x,h.mean(1),'--',color='#7f8c8d',lw=1,label='5y avg')
    ax.plot(x,d[2025],color=C25,lw=1.3,label='2025')
    c=d[2026].dropna(); ax.plot(c.index,c.values,color=C26,lw=2.3,label='2026')
    ax.plot(c.index[-1],c.values[-1],'o',color=C26); ax.annotate(f'{c.values[-1]:,.1f}' if c.values[-1]<200 else f'{c.values[-1]:,.0f}',(c.index[-1],c.values[-1]),xytext=(5,4),textcoords='offset points',color=C26,fontweight='bold')
    ax.set_xticks([1,9,18,27,36,44,52]); ax.set_xticklabels(['Jan','Mar','May','Jul','Sep','Nov','Dec'])
    ax.set_title(title,fontweight='bold',loc='left'); ax.set_ylabel(unit); ax.grid(alpha=.25)
def padd(ax,pref,title):
    labs=[('p1a','1A New Eng'),('p1b','1B C.Atl'),('p1c','1C L.Atl'),('p2','2 Midwest'),('p3','3 Gulf'),('p4','4 Rockies'),('p5','5 W.Coast')]
    def same(col,yr):
        s=df[col].dropna(); return s.iloc[np.abs(s.index-T.replace(year=yr)).argmin()]
    vs5=[(df.loc[T,f'{pref}_{k}']-np.mean([same(f'{pref}_{k}',y) for y in range(2021,2026)]))/1000 for k,_ in labs]
    yy=[(df.loc[T,f'{pref}_{k}']-same(f'{pref}_{k}',2025))/1000 for k,_ in labs]
    x=np.arange(len(labs)); 
    ax.bar(x-.2,vs5,.4,color=[C26 if v<0 else '#27ae60' for v in vs5],label='vs 5y avg')
    ax.bar(x+.2,yy,.4,color='none',edgecolor=C25,hatch='///',label='vs last year')
    for i,v in enumerate(vs5): ax.text(i-.2,v,f'{v:+.1f}',ha='center',va='bottom' if v>=0 else 'top',fontsize=8)
    ax.axhline(0,color='k',lw=.6); ax.set_xticks(x); ax.set_xticklabels([l for _,l in labs],rotation=25,fontsize=8)
    ax.set_title(title,fontweight='bold',loc='left'); ax.set_ylabel('mb'); ax.legend(fontsize=8,frameon=False); ax.grid(axis='y',alpha=.25)
for p,name,dem in [('gas','Gasoline','Finished gasoline'),('dist','Distillate','Distillate')]:
    fig,ax=plt.subplots(2,3,figsize=(16,8.6))
    seas(ax[0,0],df[f'{p}_stk']/1000,f'Total {name.lower()} stocks','mb')
    seas(ax[0,1],df[f'{p}_dem'].rolling(4).mean(),f'{dem} implied demand, 4-wk avg','kb/d')
    seas(ax[0,2],df[f'{p}_prod'].rolling(4).mean(),'Refiner & blender production, 4-wk avg','kb/d')
    seas(ax[1,0],df[f'{p}_net_exp'].rolling(4).mean(),'Net exports (exports − imports), 4-wk avg','kb/d')
    seas(ax[1,1],df[f'{p}_days'],'Days of demand cover','days')
    padd(ax[1,2],f'{p}_stk',f'Stocks by PADD vs 5y avg / last year, {T:%d %b}')
    ax[0,0].legend(loc='best',fontsize=8,frameon=False)
    fig.suptitle(f'US {name}: EIA weekly, week ending {T:%d %b %Y}',fontsize=13,fontweight='bold',x=.01,ha='left')
    fig.tight_layout(rect=(0,0,1,.95)); fig.savefig(f'us_{p}_wk.png',dpi=130); print('ok',p)
