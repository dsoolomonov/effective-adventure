import pandas as pd, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
o=pd.read_pickle('out.pkl')
M=[f'{m:02d}' for m in range(1,13)]; ML='J F M A M J J A S O N D'.split()
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
C26,C25='#c0392b','#2c3e50'
def seas(ax,tot,title,unit,div=1):
    h=np.array([[tot.get(f'{y}-{m}',np.nan)/div for m in M] for y in range(2021,2026)])
    x=np.arange(12)
    ax.fill_between(x,np.nanmin(h,0),np.nanmax(h,0),color='#bdc3c7',alpha=.6,label='2021-25 range')
    ax.plot(x,np.nanmean(h,0),'--',color='#7f8c8d',lw=1,label='5y avg')
    ax.plot(x,h[-1],color=C25,lw=1.5,label='2025')
    y26=[tot.get(f'2026-{m}',np.nan)/div for m in M[:8]]
    ax.plot(x[:8],y26,color=C26,lw=2.4,marker='o',ms=3,label='2026')
    ax.annotate(f'{y26[-1]:,.0f}',(7,y26[-1]),xytext=(5,-3),textcoords='offset points',color=C26,fontweight='bold')
    ax.set_xticks(x); ax.set_xticklabels(ML); ax.set_title(title,fontweight='bold',loc='left'); ax.set_ylabel(unit); ax.grid(alpha=.25)
def bars(ax,ss,title,n=8):
    d=(ss['2026-08']-ss['2025-08']).sort_values()
    d=pd.concat([d.head(n//2+1),d.tail(n//2)]) if len(d)>n else d
    d=d[~d.index.duplicated()]
    ax.barh(d.index,d.values,color=[C26 if v<0 else '#27ae60' for v in d.values])
    for i,v in enumerate(d.values): ax.text(v,i,f' {v:+.0f}',va='center',ha='left' if v>=0 else 'right',fontsize=8)
    ax.axvline(0,color='k',lw=.6); ax.set_title(title,fontweight='bold',loc='left'); ax.set_xlabel('kb/d'); ax.grid(axis='x',alpha=.25)
    lo,hi=ax.get_xlim(); ax.set_xlim(lo*1.25,hi*1.25 if hi>0 else 10)
for p,name in [('GASOLINE','Gasoline'),('GASDIES','Diesel / gasoil')]:
    t=lambda f:o[(p,f)]['tot']
    fig,ax=plt.subplots(2,3,figsize=(16,8.6))
    seas(ax[0,0],t('TOTDEMO'),'Demand','kb/d')
    seas(ax[0,1],t('REFGROUT'),'Refinery output','kb/d')
    seas(ax[0,2],t('TOTEXPSB')-t('TOTIMPSB'),'Net exports (exports − imports)','kb/d')
    seas(ax[1,0],t('CLOSTLV'),'Closing stocks','mb',1000)
    bars(ax[1,1],o[(p,'TOTDEMO')]['ss'],'Demand y/y by country, Aug-26')
    bars(ax[1,2],o[(p,'REFGROUT')]['ss'],'Refinery output y/y by country, Aug-26')
    ax[0,0].legend(loc='lower left',fontsize=8,frameon=False)
    fig.suptitle(f'Europe {name} balance (JODI, to Aug 2026; 26 reporting countries, matched sample)',fontsize=13,fontweight='bold',x=.01,ha='left')
    fig.tight_layout(rect=(0,0,1,.95)); fig.savefig(f'europe_{p.lower()}.png',dpi=130); print('ok',p)
