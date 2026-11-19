import json, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
exec(open('fxasia.py').read().split("def win")[0])
def win(a,b): return [x for x in r if a<=x['FixtureDate'][:10]<=b and x['CargoGroup']=='Dirty']
def mb(xs): return sum((x['QuantityInBarrels'] or 0) for x in xs)/1e6
W={'5-11 Oct':('2026-10-05','2026-10-11'),'12-19 Oct':('2026-10-12','2026-10-19')}
regs=['China','India/Pak','Sing/Malaysia','Korea','Japan','Taiwan','SE Asia other']
fig,ax=plt.subplots(1,2,figsize=(13,5))
import numpy as np
x=np.arange(len(regs)); 
for i,(k,(a,b)) in enumerate(W.items()):
  w=win(a,b); ax[0].bar(x+i*0.4-0.2,[mb([y for y in w if ASIA.get(y['LastDischargePortLevel0AreaName'])==g]) for g in regs],0.4,label=k)
ax[0].set_xticks(x); ax[0].set_xticklabels(regs,rotation=20); ax[0].set_ylabel('mb fixed'); ax[0].set_title('Dirty fixtures to Asia by destination (mb, ex Failed)'); ax[0].legend()
cls=['VLCC','Suezmax','Aframax']; x=np.arange(3)
for i,(k,(a,b)) in enumerate(W.items()):
  w=win(a,b); a_=[mb([y for y in w if y['VesselClass']==c and y['LastDischargePortLevel0AreaName'] in ASIA]) for c in cls]; t=[mb([y for y in w if y['VesselClass']==c]) for c in cls]
  bars=ax[1].bar(x+i*0.4-0.2,a_,0.4,label=k+' to Asia'); ax[1].bar(x+i*0.4-0.2,[tt-aa for tt,aa in zip(t,a_)],0.4,bottom=a_,color='lightgrey',edgecolor=bars[0].get_facecolor())
  for j in range(3): ax[1].text(x[j]+i*0.4-0.2,t[j]+1,f"{100*a_[j]/t[j]:.0f}%",ha='center',fontsize=9)
ax[1].set_xticks(x); ax[1].set_xticklabels(cls); ax[1].set_title('Asia share by class (grey = non-Asia)'); ax[1].legend()
fig.suptitle('Signal fixtures (VLCC/Suez/Afra, dirty) - fixture dates 5-19 Oct 2026, pulled 19 Oct'); fig.tight_layout(); fig.savefig('/home/ubuntu/sig/fixtures_asia_19oct.png',dpi=110)
