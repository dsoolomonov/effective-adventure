from load import *
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import LineChart, BarChart, Reference, Series
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule, FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils import get_column_letter as CL
import datetime as dt
d=load(); KEYS=[v[0] for v in META.values()]; NI=len(KEYS)
HDR=PatternFill('solid',fgColor='1F2937'); HF=Font(bold=True,color='FFFFFF'); INP=Font(color='0000FF'); YEL=PatternFill('solid',fgColor='FFF2CC')
T=Font(bold=True,size=14,color='1F4E79'); B=Font(bold=True)
def hdr(ws,r,cols,c0=1):
    for i,h in enumerate(cols): x=ws.cell(r,c0+i,h); x.fill=HDR; x.font=HF; x.alignment=Alignment(horizontal='center',wrap_text=True,vertical='center')
wb=Workbook()
# ---------- Procedure
P=wb.active; P.title='Procedure'
lines=[("Brent complex session analysis — Asia / Europe / US hours (Dubai time)",T),
("Purpose: split every spread/crack move into the session it happened in, test cross-market correlation, and check prices against our research (Signal fixtures, refinery outage pack, Asia balances).",None),
("",None),("Contract map (as per desk, 20 Oct 2026)",B),
("• CO1 = Brent Dec (reference for all cracks). CO1-CO2 = Dec/Jan, CO2-CO3 = Jan/Feb.",None),
("• WTI CL1-CL2 = Nov/Dec but Nov is expiring (volume crossed to Dec/Jan on 16 Oct) → Dec/Jan (CL2-CL3) is the effective front from this week.",None),
("• Dubai M1 = Nov (Nov/Dec, Dec/Jan, Nov/Jan spreads). Brent-Dubai M1 = Nov, M2 = Dec. DFL M1 = Nov, M2 = Dec.",None),
("• ICE gasoil QS1 = Nov; gasoil cracks QSCO1/QSCO2 referenced to CO1 (Dec Brent). HO-GO M1 = Nov, M2 = Dec. RBOB-Brent crack referenced to Dec Brent.",None),
("",None),("Sessions (Dubai time = UTC+4; bar stamp = start of the 2h/4h bar)",B),
("• Asia 02:00–09:59 (Singapore 06:00–13:59)  • Europe 10:00–17:59 (London 07:00–14:59 BST)  • US 18:00–01:59 (NY 10:00–17:59 EDT).",None),
("• A bar that follows a gap longer than the threshold (weekend) is put in its own 'Wknd gap' bucket so Monday's open is not credited to Asia.",None),
("• Boundaries and thresholds are inputs on the Inputs sheet (yellow cells) — change them and every sheet recalculates.",None),
("",None),("How to refresh",B),
("1. Export the same Bloomberg intraday series. Paste into Data!A:D (Key, Timestamp Dubai, Last, Volume), sorted by Key then Timestamp ascending. Keys are listed on Inputs.",None),
("2. Move Inputs!B7 (window start) / B8 (week start) if needed. Columns E:N on Data are formulas — fill them down to the last row.",None),
("3. Check Validation!B2 = PASS. Then read Sessions, Daily, Corr, DayxSession (pick any key in the dropdown), Research and Read.",None),
("",None),("Method notes",B),
("• Window starts 2 Oct 02:00: all generic series rolled on 1 Oct (Brent Nov expiry 30 Sep, swaps M1 Oct→Nov), so 1 Oct moves mix contracts and are excluded.",None),
("• Session change = sum of bar-to-bar changes stamped in that session. Asia+Europe+US+Wknd gap = last − base exactly (checked on Validation).",None),
("• σ units = session change ÷ 2h-bar stdev in the window, so $/t gasoil and $/bbl crude can be compared on one chart.",None),
("• Trading day = timestamp − Asia start hour (so the Sat 00:00 US-session bar belongs to Friday). Daily close = last bar of the trading day; correlations use weekday daily changes.",None),
("• Dubai spreads print every 4h, so they have half as many bars; their session split is coarser. Volume is only in the export for Brent, WTI and gasoil spreads.",None),
("• No outright Brent/Dubai flat price in this export — the analysis is on structure, cracks and arbs.",None)]
for i,(t,f) in enumerate(lines,1):
    c=P.cell(i,1,t); c.alignment=Alignment(wrap_text=True,vertical='top')
    if f: c.font=f
P.column_dimensions['A'].width=150
# ---------- Inputs
I=wb.create_sheet('Inputs'); I['A1']='Inputs (yellow = editable)'; I['A1'].font=T
sets=[('Asia session start hour (Dubai)',2),('Europe session start hour',10),('US session start hour',18),('Weekend-gap threshold (hours)',12),
      ('Analysis window start',dt.datetime(2026,10,2,2)),('Week start',dt.datetime(2026,10,13,0)),('Chart start',dt.datetime(2026,9,21,0))]
for i,(k,v) in enumerate(sets,3):
    I.cell(i,1,k); c=I.cell(i,2,v); c.fill=YEL; c.font=INP
    if isinstance(v,dt.datetime): c.number_format='dd-mmm-yy hh:mm'
I['C7']='All series rolled on 1 Oct — keep window after the roll'
hdr(I,11,['Key','Instrument','Contract','Group','Unit','Bloomberg sheet'])
for j,(sh,(k,lab,ctr,grp,unit)) in enumerate(META.items(),12):
    for c,v in enumerate([k,lab,ctr,grp,unit,sh],1): I.cell(j,c,v)
IK0,IK1=12,11+NI
for c,w in zip('ABCDEF',[34,44,12,18,8,30]): I.column_dimensions[c].width=w
# ---------- Data
D=wb.create_sheet('Data'); hdr(D,1,['Key','Timestamp (Dubai)','Last','Volume','Prev TS','Gap h','Chg','Hour','Session','In window','In week','Trading day','Chg²','Order err'])
r=2
for k in KEYS:
    for ts,row in d[k].iterrows():
        D.cell(r,1,k); c=D.cell(r,2,ts.to_pydatetime()); c.number_format='dd-mmm-yy hh:mm'; D.cell(r,3,row.px)
        if not pd.isna(row.vol): D.cell(r,4,row.vol)
        for cc in (1,2,3,4): D.cell(r,cc).font=INP
        D.cell(r,5,f'=IF(A{r}=A{r-1},B{r-1},"")').number_format='dd-mmm hh:mm'
        D.cell(r,6,f'=IF(E{r}="","",ROUND((B{r}-E{r})*24,2))')
        D.cell(r,7,f'=IF(E{r}="","",C{r}-C{r-1})')
        D.cell(r,8,f'=HOUR(B{r})')
        D.cell(r,9,f'=IF(E{r}="","Start",IF(F{r}>Inputs!$B$6,"Wknd gap",IF(AND(H{r}>=Inputs!$B$3,H{r}<Inputs!$B$4),"Asia",IF(AND(H{r}>=Inputs!$B$4,H{r}<Inputs!$B$5),"Europe","US"))))')
        D.cell(r,10,f'=IF(AND(E{r}<>"",B{r}>=Inputs!$B$7),1,0)')
        D.cell(r,11,f'=IF(AND(E{r}<>"",B{r}>=Inputs!$B$8),1,0)')
        D.cell(r,12,f'=INT(B{r}-Inputs!$B$3/24)').number_format='dd-mmm-yy'
        D.cell(r,13,f'=IF(G{r}="","",G{r}^2)')
        D.cell(r,14,f'=IF(AND(A{r}=A{r-1},B{r}<=B{r-1}),1,0)')
        r+=1
NLAST=r-1; RMAX=8000
for c,w in zip('ABCDEFGHIJKLMN',[7,16,9,9,13,7,9,6,10,9,9,11,9,9]): D.column_dimensions[c].width=w
D.freeze_panes='A2'
names={'dKey':'A','dTS':'B','dPx':'C','dVol':'D','dChg':'G','dHour':'H','dSess':'I','dWin':'J','dWk':'K','dDay':'L','dChg2':'M','dErr':'N'}
for n,c in names.items(): wb.defined_names[n]=DefinedName(n,attr_text=f"Data!${c}$2:${c}${RMAX}")
# ---------- Sessions
S=wb.create_sheet('Sessions'); S['A1']='Session decomposition — window (from Inputs!B7) and week (from Inputs!B8)'; S['A1'].font=T
cols=['Key','Instrument','Unit','Base (last before window)','Last','Δ window','Asia','Europe','US','Wknd gap','Check Σ−Δ','2h σ','Asia σ','Europe σ','US σ','Gap σ','Driver','Vol% Asia','Vol% Europe','Vol% US',
      'Base (week)','Δ week','Asia wk','Europe wk','US wk','Gap wk','Driver wk','Hi (window)','Lo (window)']
hdr(S,3,cols)
SESS=['Asia','Europe','US','Wknd gap']
for i,k in enumerate(KEYS):
    r=4+i; ir=IK0+i
    S.cell(r,1,f'=Inputs!A{ir}'); S.cell(r,2,f'=Inputs!B{ir}'); S.cell(r,3,f'=Inputs!E{ir}')
    S.cell(r,4,f'=AVERAGEIFS(dPx,dKey,$A{r},dTS,_xlfn.MAXIFS(dTS,dKey,$A{r},dTS,"<"&Inputs!$B$7))')
    S.cell(r,5,f'=AVERAGEIFS(dPx,dKey,$A{r},dTS,_xlfn.MAXIFS(dTS,dKey,$A{r}))')
    S.cell(r,6,f'=E{r}-D{r}')
    for j,s in enumerate(SESS): S.cell(r,7+j,f'=SUMIFS(dChg,dKey,$A{r},dSess,"{s}",dWin,1)')
    S.cell(r,11,f'=ROUND(SUM(G{r}:J{r})-F{r},9)')
    n=f'COUNTIFS(dKey,$A{r},dWin,1)'
    S.cell(r,12,f'=SQRT((SUMIFS(dChg2,dKey,$A{r},dWin,1)-SUMIFS(dChg,dKey,$A{r},dWin,1)^2/{n})/({n}-1))')
    for j in range(4): S.cell(r,13+j,f'={CL(7+j)}{r}/$L{r}')
    S.cell(r,17,f'=IF(MAX(ABS(G{r}),ABS(H{r}),ABS(I{r}))=ABS(G{r}),"Asia",IF(MAX(ABS(H{r}),ABS(I{r}))=ABS(H{r}),"Europe","US"))&IF(SIGN(F{r})=SIGN(INDEX(G{r}:I{r},MATCH(MAX(ABS(G{r}),ABS(H{r}),ABS(I{r})),INDEX(ABS(G{r}:I{r}),0),0))),""," (against)")')
    for j,s in enumerate(['Asia','Europe','US']): S.cell(r,18+j,f'=IFERROR(SUMIFS(dVol,dKey,$A{r},dSess,"{s}",dWin,1)/SUMIFS(dVol,dKey,$A{r},dWin,1),"n/a")').number_format='0%'
    S.cell(r,21,f'=AVERAGEIFS(dPx,dKey,$A{r},dTS,_xlfn.MAXIFS(dTS,dKey,$A{r},dTS,"<"&Inputs!$B$8))')
    S.cell(r,22,f'=E{r}-U{r}')
    for j,s in enumerate(SESS): S.cell(r,23+j,f'=SUMIFS(dChg,dKey,$A{r},dSess,"{s}",dWk,1)')
    S.cell(r,27,f'=IF(MAX(ABS(W{r}),ABS(X{r}),ABS(Y{r}))=ABS(W{r}),"Asia",IF(MAX(ABS(X{r}),ABS(Y{r}))=ABS(X{r}),"Europe","US"))')
    S.cell(r,28,f'=_xlfn.MAXIFS(dPx,dKey,$A{r},dTS,">="&Inputs!$B$7)'); S.cell(r,29,f'=_xlfn.MINIFS(dPx,dKey,$A{r},dTS,">="&Inputs!$B$7)')
    for c in list(range(4,13))+list(range(21,27))+[28,29]: S.cell(r,c).number_format='+0.00;-0.00;0.00'
    for c in range(13,17): S.cell(r,c).number_format='+0.0;-0.0;0.0'
SR0,SR1=4,3+NI
for rng in [f'G{SR0}:J{SR1}',f'W{SR0}:Z{SR1}',f'M{SR0}:P{SR1}']:
    S.conditional_formatting.add(rng,ColorScaleRule(start_type='percentile',start_value=5,start_color='F8696B',mid_type='num',mid_value=0,mid_color='FFFFFF',end_type='percentile',end_value=95,end_color='63BE7B'))
S.column_dimensions['B'].width=40
for c in range(3,30): S.column_dimensions[CL(c)].width=10
S.column_dimensions['Q'].width=16; S.freeze_panes='C4'
ch=BarChart(); ch.type='bar'; ch.grouping='stacked'; ch.overlap=100; ch.title='Who moved it — session contribution since window start (σ units)'
data=Reference(S,min_col=13,max_col=16,min_row=3,max_row=SR1); ch.add_data(data,titles_from_data=True); ch.set_categories(Reference(S,min_col=1,min_row=SR0,max_row=SR1))
ch.height=13; ch.width=24; ch.y_axis.title='σ (2h bar stdev)'
for s,col in zip(ch.series,['F59E0B','3B82F6','EF4444','9CA3AF']): s.graphicalProperties.solidFill=col
S.add_chart(ch,f'B{SR1+3}')
ch=BarChart(); ch.type='bar'; ch.grouping='stacked'; ch.overlap=100; ch.title='Last week (since Inputs!B8) — raw change by session'
ch.add_data(Reference(S,min_col=23,max_col=26,min_row=3,max_row=SR1),titles_from_data=True); ch.set_categories(Reference(S,min_col=1,min_row=SR0,max_row=SR1)); ch.height=13; ch.width=20
for s,col in zip(ch.series,['F59E0B','3B82F6','EF4444','9CA3AF']): s.graphicalProperties.solidFill=col
S.add_chart(ch,f'N{SR1+3}')
# ---------- Daily
DL=wb.create_sheet('Daily'); DL['A1']='Daily closes (trading day = Dubai time − Asia start) and daily changes'; DL['A1'].font=T
ND=16
hdr(DL,3,['Trading day']+KEYS); hdr(DL,3,['Day']+[k+' Δ' for k in KEYS],c0=NI+3)
hdr(DL,3,['W12 vol','W23 vol','B12 vol','G12 vol'],c0=2*NI+5)
for i in range(ND):
    r=4+i
    DL.cell(r,1,'=WORKDAY(INT(Inputs!$B$7)-1,0)' if i==0 else f'=WORKDAY(A{r-1},1)').number_format='ddd dd-mmm'
    DL.cell(r,NI+3,f'=A{r}').number_format='ddd dd-mmm'
    for j,k in enumerate(KEYS):
        col=2+j
        DL.cell(r,col,f'=IFERROR(AVERAGEIFS(dPx,dKey,{CL(col)}$3,dTS,_xlfn.MAXIFS(dTS,dKey,{CL(col)}$3,dDay,$A{r})),NA())').number_format='0.00'
        if i>0: DL.cell(r,NI+4+j,f'=IFERROR({CL(col)}{r}-{CL(col)}{r-1},"")').number_format='+0.00;-0.00'
    for j,k in enumerate(['W12','W23','B12','G12']): DL.cell(r,2*NI+5+j,f'=SUMIFS(dVol,dKey,"{k}",dDay,$A{r})').number_format='#,##0'
DR0,DR1=4,3+ND
for c in range(1,2*NI+9): DL.column_dimensions[CL(c)].width=8.5
DL.column_dimensions['A'].width=12
ch=LineChart(); ch.title='WTI expiry: volume moving from Nov/Dec to Dec/Jan'; ch.add_data(Reference(DL,min_col=2*NI+5,max_col=2*NI+6,min_row=3,max_row=DR1),titles_from_data=True)
ch.set_categories(Reference(DL,min_col=1,min_row=DR0,max_row=DR1)); ch.height=8; ch.width=18; ch.y_axis.title='lots/day'
DL.add_chart(ch,f'B{DR1+3}')
# ---------- Corr
CR=wb.create_sheet('Corr'); CR['A1']='Correlation of daily changes (weekdays in Daily sheet)'; CR['A1'].font=T
hdr(CR,3,['']+KEYS)
for i,a in enumerate(KEYS):
    CR.cell(4+i,1,a).font=B
    for j,b in enumerate(KEYS):
        ca=CL(NI+4+i); cb=CL(NI+4+j)
        CR.cell(4+i,2+j,f'=IFERROR(CORREL(Daily!${ca}${DR0+1}:${ca}${DR1},Daily!${cb}${DR0+1}:${cb}${DR1}),"")').number_format='0.00'
CR.conditional_formatting.add(f'B4:{CL(1+NI)}{3+NI}',ColorScaleRule(start_type='num',start_value=-1,start_color='F8696B',mid_type='num',mid_value=0,mid_color='FFFFFF',end_type='num',end_value=1,end_color='5B9BD5'))
for c in range(2,NI+2): CR.column_dimensions[CL(c)].width=6.5
CR.cell(5+NI,1,'Reading: red = move opposite, blue = move together. Brent/Dubai/DFL structure is one block; gasoil spread/crack a second; HO-GO trades against European gasoil (US vs Europe diesel arb).')
# ---------- Grid + session paths
G=wb.create_sheet('Grid'); G['A1']='2h timeline for charts (#N/A = no bar; Excel line charts connect across it)'; G['A1'].font=T
G['A2']='Session path key →'; G['B2']='B12'; G['B2'].fill=YEL; G['B2'].font=INP
dv=DataValidation(type='list',formula1=f'=Inputs!$A${IK0}:$A${IK1}',allow_blank=False); G.add_data_validation(dv); dv.add('B2')
hdr(G,3,['Timestamp']+KEYS+['Path: Asia','Path: Europe','Path: US','Path: Wknd gap','Path: total'])
NG=420
for i in range(NG):
    r=4+i
    if i==0: G.cell(r,1,'=_xlfn.MINIFS(dTS,dTS,">="&Inputs!$B$9)')
    else: G.cell(r,1,f'=IF(A{r-1}="","",IF(_xlfn.MINIFS(dTS,dTS,">"&A{r-1})=0,"",_xlfn.MINIFS(dTS,dTS,">"&A{r-1})))')
    G.cell(r,1).number_format='dd-mmm hh:mm'
    for j,k in enumerate(KEYS):
        G.cell(r,2+j,f'=IF($A{r}="",NA(),IFERROR(AVERAGEIFS(dPx,dKey,{CL(2+j)}$3,dTS,$A{r}),NA()))').number_format='0.00'
    for j,s in enumerate(SESS):
        c=NI+2+j; prev='0' if i==0 else f'{CL(c)}{r-1}'
        G.cell(r,c,f'=IF($A{r}="",NA(),{prev}+SUMIFS(dChg,dKey,$B$2,dTS,$A{r},dSess,"{s}",dWin,1))').number_format='+0.00;-0.00'
    G.cell(r,NI+6,f'=IF($A{r}="",NA(),SUM({CL(NI+2)}{r}:{CL(NI+5)}{r}))').number_format='+0.00;-0.00'
G.freeze_panes='B4'; GR0,GR1=4,3+NG
# ---------- DayxSession
X=wb.create_sheet('DayxSession'); X['A1']='Day × session change for the selected key'; X['A1'].font=T
X['A2']='Key'; X['B2']='G12'; X['B2'].fill=YEL; X['B2'].font=INP
dv2=DataValidation(type='list',formula1=f'=Inputs!$A${IK0}:$A${IK1}'); X.add_data_validation(dv2); dv2.add('B2')
X['C2']='=INDEX(Inputs!$B${0}:$B${1},MATCH($B$2,Inputs!$A${0}:$A${1},0))'.format(IK0,IK1)
hdr(X,4,['Trading day']+SESS+['Day total'])
for i in range(ND):
    r=5+i; X.cell(r,1,f'=Daily!A{DR0+i}').number_format='ddd dd-mmm'
    for j,s in enumerate(SESS): X.cell(r,2+j,f'=SUMIFS(dChg,dKey,$B$2,dDay,$A{r},dSess,"{s}",dWin,1)').number_format='+0.00;-0.00;–'
    X.cell(r,6,f'=SUM(B{r}:E{r})').number_format='+0.00;-0.00;–'
X.cell(6+ND,1,'Total').font=B
for j in range(5): X.cell(6+ND,2+j,f'=SUM({CL(2+j)}5:{CL(2+j)}{4+ND})').number_format='+0.00;-0.00'
X.conditional_formatting.add(f'B5:E{4+ND}',ColorScaleRule(start_type='min',start_color='F8696B',mid_type='num',mid_value=0,mid_color='FFFFFF',end_type='max',end_color='63BE7B'))
X.column_dimensions['A'].width=13; X.column_dimensions['C'].width=12
ch=BarChart(); ch.grouping='stacked'; ch.overlap=100; ch.title='Daily change split by session (selected key)'
ch.add_data(Reference(X,min_col=2,max_col=5,min_row=4,max_row=4+ND),titles_from_data=True); ch.set_categories(Reference(X,min_col=1,min_row=5,max_row=4+ND)); ch.height=9; ch.width=20
for s,col in zip(ch.series,['F59E0B','3B82F6','EF4444','9CA3AF']): s.graphicalProperties.solidFill=col
X.add_chart(ch,'H4')
# ---------- VolHour
V=wb.create_sheet('VolHour'); V['A1']='Where the liquidity is — volume by bar hour (Dubai), window'; V['A1'].font=T
VK=['B12','B23','W12','W23','G12']
hdr(V,3,['Hour (Dubai)']+VK)
for i,h in enumerate(range(0,24,2)):
    r=4+i; V.cell(r,1,h)
    for j,k in enumerate(VK): V.cell(r,2+j,f'=SUMIFS(dVol,dKey,"{k}",dHour,$A{r},dWin,1)').number_format='#,##0'
ch=BarChart(); ch.title='Volume by hour (Dubai) — Asia 02–10, Europe 10–18, US 18–02'; ch.add_data(Reference(V,min_col=2,max_col=1+len(VK),min_row=3,max_row=15),titles_from_data=True)
ch.set_categories(Reference(V,min_col=1,min_row=4,max_row=15)); ch.height=9; ch.width=20; V.add_chart(ch,'H3')
# ---------- Charts
CH=wb.create_sheet('Charts'); CH['A1']='Charts (source: Grid). Change Grid!B2 to redraw the session path.'; CH['A1'].font=T
def line(title,keys,anchor,ytitle):
    c=LineChart(); c.title=title; c.height=8.5; c.width=17; c.y_axis.title=ytitle; c.x_axis.number_format='dd-mmm'
    for k in keys:
        col=2+KEYS.index(k); s=Series(Reference(G,min_col=col,min_row=GR0,max_row=GR1),title=META_L[k]); s.smooth=False; s.graphicalProperties.line.width=15000; c.series.append(s)
    c.set_categories(Reference(G,min_col=1,min_row=GR0,max_row=GR1)); c.x_axis.tickLblSkip=24; CH.add_chart(c,anchor)
META_L={v[0]:v[1] for v in META.values()}
line('Brent spreads (CO1 = Dec)',['B12','B23','B13'],'A3','$/bbl')
line('WTI spreads (Nov expiring → Dec/Jan front)',['W12','W23','W34'],'K3','$/bbl')
line('Dubai spreads (M1 = Nov)',['D12','D23','D13'],'A21','$/bbl')
line('Brent-Dubai EFS & DFL',['BD1','BD2','DFL1','DFL2'],'K21','$/bbl')
line('ICE gasoil spreads',['G12','G23'],'A39','$/t')
line('Cracks vs Dec Brent',['GC1','GC2','RC1','RC2'],'K39','$/bbl')
line('HO-GO (US vs Europe diesel)',['HG1','HG2'],'A57','$/t')
c=LineChart(); c.title='Session path — cumulative change by session (key in Grid!B2)'; c.height=8.5; c.width=17
c.add_data(Reference(G,min_col=NI+2,max_col=NI+6,min_row=3,max_row=GR1),titles_from_data=True); c.set_categories(Reference(G,min_col=1,min_row=GR0,max_row=GR1)); c.x_axis.tickLblSkip=24
for s,col in zip(c.series,['F59E0B','3B82F6','EF4444','9CA3AF','111827']): s.graphicalProperties.line.solidFill=col; s.graphicalProperties.line.width=20000
CH.add_chart(c,'K57')
exec(open('part2.py').read())
