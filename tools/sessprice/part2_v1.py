ORDER=['Procedure','Read','Inputs','Sessions','Charts','DayxSession','Daily','Corr','VolHour','Research','Grid','Data','Validation']
KR={k:SR0+i for i,k in enumerate(KEYS)}  # Sessions row per key
def sref(k,col): return f'Sessions!${col}${KR[k]}'
# ---------- Research
R=wb.create_sheet('Research'); R['A1']='Research vs price — does the tape confirm what our research says?'; R['A1'].font=T
R['A2']='Research numbers are inputs (blue). "Expected sign" = direction the research implies for the test instrument. Verdict compares with the price change in the chosen horizon.'
hdr(R,4,['Theme','Source','What the research says','Test key','Horizon','Expected sign','Price Δ','Unit','Session driver','Verdict'])
RES=[('Asia pull on Middle East crude','Signal fixtures 12–19 Oct','43/46 VLCCs to Asia; 109/214 mb dirty to Asia; ~15 mb to China on 19 Oct (AMCL COA). Should firm Dubai structure.','D12','week',1),
('Asia pull → Dubai over Brent','Signal fixtures 12–19 Oct','Same flow: Brent-Dubai EFS should fall (Dubai stronger).','BD1','week',-1),
('Crude runs return Nov–Dec','Refinery outage pack 8 Oct','Global crude offline 11.1 → 7.4 → 5.6 mb/d Oct–Dec; Nov–Mar revised −651 kb/d. Supports prompt Brent structure.','B12','window',1),
('Physical Brent bid','Refinery outage pack + Dated tab','North Sea runs back + Dec DFL skeleton 365 vs 355 quoted → DFL Dec should firm.','DFL2','window',1),
('Conversion units tight','Refinery outage pack 8 Oct','FCC +393 / coking +357 kb/d revised up Nov–Mar → cracks over crude spreads.','GC1','window',1),
('Middle distillates drawing','Asia balances 8 Oct','Asia gasoil long 785 kb/d but stocks 126.5 → 107.4 mb Aug–Dec → constructive gasoil spreads.','G12','week',1),
('Gasoline length','Asia balances 8 Oct','China demand −248 kb/d; Asia gasoline stocks build 76.8 → 82.2 mb Oct–Dec → fade gasoline.','RC1','window',-1),
('Diesel arb East→West','Asia balances 8 Oct','China permits withheld pull India east, less to Europe → Europe tighter vs US → HO-GO down.','HG1','window',-1),
('WTI prompt expiry','Market structure','CL Nov expires 20 Oct; volume crossed to Dec/Jan 16 Oct → prompt squeeze, US hours.','W12','week',1)]
for i,(th,src,txt,k,hz,sg) in enumerate(RES):
    r=5+i
    for c,v in enumerate([th,src,txt,k,hz,sg],1):
        x=R.cell(r,c,v); x.alignment=Alignment(wrap_text=True,vertical='top')
        if c in (4,5,6): x.font=INP; x.fill=YEL
    R.cell(r,7,f'=IF(E{r}="week",INDEX(Sessions!$V${SR0}:$V${SR1},MATCH(D{r},Sessions!$A${SR0}:$A${SR1},0)),INDEX(Sessions!$F${SR0}:$F${SR1},MATCH(D{r},Sessions!$A${SR0}:$A${SR1},0)))').number_format='+0.00;-0.00'
    R.cell(r,8,f'=INDEX(Sessions!$C${SR0}:$C${SR1},MATCH(D{r},Sessions!$A${SR0}:$A${SR1},0))')
    R.cell(r,9,f'=IF(E{r}="week",INDEX(Sessions!$AA${SR0}:$AA${SR1},MATCH(D{r},Sessions!$A${SR0}:$A${SR1},0)),INDEX(Sessions!$Q${SR0}:$Q${SR1},MATCH(D{r},Sessions!$A${SR0}:$A${SR1},0)))')
    R.cell(r,10,f'=IF(ABS(G{r})<0.5*INDEX(Sessions!$L${SR0}:$L${SR1},MATCH(D{r},Sessions!$A${SR0}:$A${SR1},0)),"Flat",IF(SIGN(G{r})=F{r},"Confirms","Contradicts"))')
RL=4+len(RES)
R.conditional_formatting.add(f'J5:J{RL}',CellIsRule(operator='equal',formula=['"Confirms"'],fill=PatternFill('solid',fgColor='C6EFCE')))
R.conditional_formatting.add(f'J5:J{RL}',CellIsRule(operator='equal',formula=['"Contradicts"'],fill=PatternFill('solid',fgColor='FFC7CE')))
R.cell(RL+2,1,'Score'); R.cell(RL+2,2,f'=COUNTIF(J5:J{RL},"Confirms")&" confirm / "&COUNTIF(J5:J{RL},"Contradicts")&" contradict / "&COUNTIF(J5:J{RL},"Flat")&" flat"')
for c,w in zip('ABCDEFGHIJ',[28,26,70,8,9,9,9,6,14,12]): R.column_dimensions[c].width=w
# ---------- Read (numbers by formula)
RD=wb.create_sheet('Read'); RD['A1']='Desk read — numbers pull live from Sessions (σ = 2h-bar stdev)'; RD['A1'].font=T
f=lambda k,c: f'TEXT({sref(k,c)},"+0.00;-0.00")'
reads=[
 '="Brent Dec/Jan "&TEXT('+sref('B12','E')+',"0.00")&" ("&'+f('B12','F')+'&" since 2 Oct; week "&'+f('B12','V')+'&"). Europe hours "&'+f('B12','H')+'&", US hours "&'+f('B12','I')+'&", week Europe "&'+f('B12','X')+'&" / US "&'+f('B12','Y')+'&": London sells structure, NY buys it back."',
 '="Dubai Nov/Dec "&TEXT('+sref('D12','E')+',"0.00")&" ("&'+f('D12','F')+'&"): Asia hours "&'+f('D12','G')+'&" (week "&'+f('D12','W')+'&"). Asia is selling Dubai structure in its own session even with 43/46 VLCCs fixed to Asia — the fixtures are term/COA barrels, not spot bids."',
 '="Brent-Dubai Nov "&TEXT('+sref('BD1','E')+',"0.00")&" (week "&'+f('BD1','V')+'&"): Dubai premium narrowing. Brent Dec/Jan vs Dubai Nov/Dec daily corr = "&TEXT(Corr!H4,"0.00")&" — east and west structure is one trade; the EFS is the residual."',
 '="DFL Nov "&TEXT('+sref('DFL1','E')+',"0.00")&" / Dec "&TEXT('+sref('DFL2','E')+',"0.00")&" ("&'+f('DFL2','F')+'&" since 2 Oct, Europe hours "&'+f('DFL2','H')+'&"): physical holding up vs paper; DFL Dec tracks Dec/Jan (corr "&TEXT(Corr!N4,"0.00")&")."',
 '="WTI Nov/Dec "&TEXT('+sref('W12','E')+',"0.00")&" (week "&'+f('W12','V')+'&", US hours "&'+f('W12','Y')+'&") = expiry squeeze into 20 Oct. Dec/Jan, the real front now, "&'+f('W23','V')+'&" on the week, "&TEXT('+sref('W23','T')+',"0%")&" of its volume in US hours."',
 '="Gasoil Nov/Dec "&TEXT('+sref('G12','E')+',"0.00")&" $/t: week "&'+f('G12','V')+'&" = US hours "&'+f('G12','Y')+'&" vs Asia "&'+f('G12','W')+'&". Nov crack "&TEXT('+sref('GC1','E')+',"0.00")&" ("&'+f('GC1','F')+'&"): Asia "&'+f('GC1','G')+'&", US "&'+f('GC1','I')+'&". Asia sells distillate, the US bids it — matches the long-but-drawing Asia gasoil balance."',
 '="RBOB-Brent "&TEXT('+sref('RC1','E')+',"0.00")&" ("&'+f('RC1','F')+'&", US hours "&'+f('RC1','I')+'&"): gasoline is the weak link, in line with the Asia gasoline stock build and China demand −248 kb/d."',
 '="HO-GO Nov "&TEXT('+sref('HG1','E')+',"0.00")&" $/t ("&'+f('HG1','F')+'&"): Asia+Europe "&TEXT('+sref('HG1','G')+'+'+sref('HG1','H')+',"+0.00;-0.00")&", US "&'+f('HG1','I')+'&". Europe weak vs US diesel in European hours; daily corr with gasoil Nov/Dec "&TEXT(Corr!O23,"0.00")&"."',
 '="Trade: buy Brent Dec/Jan on London-hours weakness and lighten into NY; buy gasoil Nov crack in Asian hours (Asia has sold "&'+f('GC1','W')+'&" this week, US bought "&'+f('GC1','Y')+'&"); stay short RBOB-Brent. Kill: Asia-hours selling of cracks stops while Dubai Nov/Dec falls below 3.00."',
 'Caveats: 13 weekday daily changes only — correlations are indicative. No outright flat price in the export. Dubai prints 4-hourly. Volume only for Brent/WTI/gasoil spreads.']
for i,t in enumerate(reads):
    c=RD.cell(3+i,1,t); c.alignment=Alignment(wrap_text=True,vertical='top'); RD.row_dimensions[3+i].height=48
RD.column_dimensions['A'].width=160
# ---------- Validation
VA=wb.create_sheet('Validation'); VA['A1']='Validation'; VA['A1'].font=T; VA['A2']='Overall'
hdr(VA,4,['Check','Value','Expected','Result'])
cnt={k:len(d[k]) for k in KEYS}
checks=[('Session boundaries ordered (Asia < Europe < US ≤ 24)','=AND(Inputs!B3<Inputs!B4,Inputs!B4<Inputs!B5,Inputs!B5<=24)','TRUE','=IF(B{r}=TRUE,"PASS","FAIL")'),
 ('Timestamps strictly increasing within each key','=SUM(dErr)',0,'=IF(B{r}=0,"PASS","FAIL")'),
 ('Every bar has a session label','=COUNTIF(dSess,"Asia")+COUNTIF(dSess,"Europe")+COUNTIF(dSess,"US")+COUNTIF(dSess,"Wknd gap")+COUNTIF(dSess,"Start")-COUNTA(dKey)',0,'=IF(B{r}=0,"PASS","FAIL")'),
 ('One "Start" row per key',f'=COUNTIF(dSess,"Start")',NI,'=IF(B{r}=C{r},"PASS","FAIL")'),
 ('Σ sessions = Δ window, all keys (max abs error)',f'=SUMPRODUCT(ABS(Sessions!K{SR0}:K{SR1}))',0,'=IF(B{r}<0.000001,"PASS","FAIL")'),
 ('Σ week sessions = Δ week, all keys',f'=SUMPRODUCT(ABS(Sessions!W{SR0}:W{SR1}+Sessions!X{SR0}:X{SR1}+Sessions!Y{SR0}:Y{SR1}+Sessions!Z{SR0}:Z{SR1}-Sessions!V{SR0}:V{SR1}))',0,'=IF(B{r}<0.000001,"PASS","FAIL")'),
 ('Correlation diagonal = 1','='+'+'.join(f'Corr!{CL(2+i)}{4+i}' for i in range(NI)),NI,'=IF(ABS(B{r}-C{r})<0.000001,"PASS","FAIL")'),
 ('Grid ends at last timestamp in Data','=MAX(Grid!A4:A423)-MAX(dTS)',0,'=IF(ABS(B{r})<0.0001,"PASS","FAIL")'),
 ('Grid has spare rows for refresh',f'=COUNTBLANK(Grid!A4:A423)','>0','=IF(B{r}>0,"PASS","FAIL")'),
 ('Data rows inside named ranges',f'=COUNTA(dKey)',sum(cnt.values()),'=IF(B{r}=C{r},"PASS","FAIL")')]
for k in KEYS:
    j=KEYS.index(k)
    checks.append((f'{k}: bars loaded = Bloomberg sheet rows',f'=COUNTIF(dKey,"{k}")',cnt[k],'=IF(B{r}=C{r},"PASS","FAIL")'))
    checks.append((f'{k}: last daily close = last bar',f'=LOOKUP(9.99E+307,Daily!{CL(2+j)}{DR0}:{CL(2+j)}{DR1})-Sessions!E{SR0+j}',0,'=IF(ABS(B{r})<0.000001,"PASS","FAIL")'))
for i,(n,v,e,res) in enumerate(checks):
    r=5+i; VA.cell(r,1,n); VA.cell(r,2,v); VA.cell(r,3,e); VA.cell(r,4,res.format(r=r))
VL=4+len(checks)
VA['B2']=f'=IF(COUNTIF(D5:D{VL},"PASS")={len(checks)},"PASS","FAIL — "&COUNTIF(D5:D{VL},"FAIL")&" check(s)")'; VA['B2'].font=Font(bold=True,size=13)
VA.conditional_formatting.add(f'D5:D{VL}',CellIsRule(operator='equal',formula=['"PASS"'],fill=PatternFill('solid',fgColor='C6EFCE')))
VA.conditional_formatting.add(f'D5:D{VL}',CellIsRule(operator='equal',formula=['"FAIL"'],fill=PatternFill('solid',fgColor='FFC7CE')))
VA.column_dimensions['A'].width=55; VA.column_dimensions['B'].width=14
wb._sheets.sort(key=lambda s: ORDER.index(s.title))
wb.active=0
wb.save('Brent_session_analysis_20Oct.xlsx'); print('saved',len(checks),'checks')
