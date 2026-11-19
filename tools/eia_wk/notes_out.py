import pandas as pd,numpy as np,matplotlib
matplotlib.use('Agg');import matplotlib.pyplot as plt
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
t=pd.read_pickle('yoy.pkl');yrs=[2026,2025,2024,2023,2022,2021]
wb=Workbook();ws=wb.active;ws.title='Same-week comparison'
ws['A1']='US EIA WPSR — gasoline & distillate, week ending 16 Oct 2026 vs same week in prior years';ws['A1'].font=Font(bold=True,size=13)
ws['A2']='Same weeks: 17-Oct-25, 18-Oct-24, 13-Oct-23, 14-Oct-22, 15-Oct-21. 5y avg = 2021-25 mean. Rank: 1 = lowest of 6 years, 6 = highest. Source: EIA WPSR tables; 4w avgs, net exports, days cover calculated.'
ws['A2'].font=Font(italic=True,size=9)
hdr=['Item','Unit']+[str(y) for y in yrs]+['5y avg','vs 2025','vs 5y','Rank /6']
for j,h in enumerate(hdr,1):
    c=ws.cell(4,j,h);c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='2C3E50');c.alignment=Alignment(horizontal='center')
r=5;sec=None
for _,x in t.iterrows():
    s='Gasoline' if x['item'].startswith(('Gas','  ','   ','Blend')) and r<5+23 else ('Distillate' if r<5+43+2 else 'Refining')
    vals=[x['item'].strip() if not x['item'].startswith(' ') else x['item'],x['unit']]+[x[y] for y in yrs]+[x['5y'],x['vs25'],x['vs5y'],int(x['rank'])]
    for j,v in enumerate(vals,1):
        c=ws.cell(r,j,v)
        if j>=3 and j<=11: c.number_format='#,##0.0;[Red]-#,##0.0' if x['unit'] in('mb','d','%') else '#,##0;[Red]-#,##0'
        if j==3: c.font=Font(bold=True);c.fill=PatternFill('solid',fgColor='FDEBD0')
        if j==12:
            c.alignment=Alignment(horizontal='center')
            if v==1: c.fill=PatternFill('solid',fgColor='F5B7B1')
            if v==6: c.fill=PatternFill('solid',fgColor='ABEBC6')
    if not x['item'].startswith(' '): ws.cell(r,1).font=Font(bold=True)
    r+=1
ws.column_dimensions['A'].width=22
for col in 'BCDEFGHIJKL': ws.column_dimensions[col].width=10
ws.freeze_panes='C5';wb.save('EIA_WPSR_16Oct26_same_week_vs_prior_years.xlsx')
# chart: key components across years
keys=[('Gasoline total stocks','Gasoline stocks (mb)'),('Gas imp 4w','Gasoline imports 4w (kb/d)'),('Gas demand 4w','Gasoline demand 4w (kb/d)'),('Gas prod 4w','Gasoline production 4w (kb/d)'),
('Dist total stocks','Distillate stocks (mb)'),('Dist demand 4w','Distillate demand 4w (kb/d)'),('Dist prod 4w','Distillate production 4w (kb/d)'),('Dist exp 4w','Distillate exports 4w (kb/d)')]
fig,ax=plt.subplots(2,4,figsize=(17,7.5));plt.rcParams.update({'font.size':9})
tt=t.set_index(t['item'].str.strip())
for a,(k,ttl) in zip(ax.flat,keys):
    x=tt.loc[k] if not isinstance(tt.loc[k],pd.DataFrame) else tt.loc[k].iloc[0]
    v=[x[y] for y in yrs[::-1]];cl=['#95a5a6']*5+['#c0392b']
    b=a.bar([str(y) for y in yrs[::-1]],v,color=cl);a.axhline(x['5y'],ls='--',color='k',lw=.8)
    lo,hi=min(v),max(v);a.set_ylim(lo-(hi-lo)*.6,hi+(hi-lo)*.25)
    for bb,vv in zip(b,v): a.text(bb.get_x()+bb.get_width()/2,vv,f'{vv:,.1f}' if vv<300 else f'{vv:,.0f}',ha='center',va='bottom',fontsize=8)
    a.set_title(ttl,fontweight='bold',loc='left');a.spines[['top','right']].set_visible(False)
fig.suptitle('Same week (mid-Oct) 2021–2026: 2026 in red, dashed = 2021–25 avg',fontweight='bold',x=.01,ha='left',fontsize=12)
fig.tight_layout(rect=(0,0,1,.95));fig.savefig('us_same_week_years.png',dpi=130)
# 2026 gasoline table check row for padd1 dist
print(tt.loc[['PADD1','PADD3']][[2026,2025,2024,'rank']])
