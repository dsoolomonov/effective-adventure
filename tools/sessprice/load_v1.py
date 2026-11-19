import openpyxl, pandas as pd, numpy as np, json
SRC='/home/ubuntu/attachments/d44863b3-2cf9-40ce-b30e-31b7ed92bab8/pricingsss.xlsx'
# sheet -> (key, label, contract, group, unit)
META={
 'CO1CO2':('B12','Brent Dec/Jan (CO1-CO2)','Dec/Jan','Crude spreads','$/bbl'),
 'CO2CO3':('B23','Brent Jan/Feb (CO2-CO3)','Jan/Feb','Crude spreads','$/bbl'),
 'CO1CO3':('B13','Brent Dec/Feb (CO1-CO3)','Dec/Feb','Crude spreads','$/bbl'),
 'WTI NOV DEC spread':('W12','WTI Nov/Dec (CL1-CL2, expiring)','Nov/Dec','Crude spreads','$/bbl'),
 'WTI dec jan spread':('W23','WTI Dec/Jan (CL2-CL3, effective front)','Dec/Jan','Crude spreads','$/bbl'),
 'WTI Jan Feb Spread':('W34','WTI Jan/Feb (CL3-CL4)','Jan/Feb','Crude spreads','$/bbl'),
 'Dubai Novdec (m1m2) SPREAD':('D12','Dubai Nov/Dec','Nov/Dec','Dubai / East-West','$/bbl'),
 'Dubai Dec Jan (m2m3) spread':('D23','Dubai Dec/Jan','Dec/Jan','Dubai / East-West','$/bbl'),
 'Dubai Nov Jan Spread (m1m3)':('D13','Dubai Nov/Jan','Nov/Jan','Dubai / East-West','$/bbl'),
 'BrentDubai m1 (Nov)':('BD1','Brent-Dubai Nov','Nov','Dubai / East-West','$/bbl'),
 'Brent Dubai m2(Dec)':('BD2','Brent-Dubai Dec','Dec','Dubai / East-West','$/bbl'),
 'DFL M1 (NOV)':('DFL1','DFL Nov (Dated - front line)','Nov','Brent physical','$/bbl'),
 'DFL M2 (DEC)':('DFL2','DFL Dec','Dec','Brent physical','$/bbl'),
 'QS1QS2':('G12','ICE Gasoil Nov/Dec (QS1-QS2)','Nov/Dec','Products','$/t'),
 'QS2QS3':('G23','ICE Gasoil Dec/Jan (QS2-QS3)','Dec/Jan','Products','$/t'),
 'Gasoil crack 1':('GC1','Gasoil Nov crack vs Brent Dec (QSCO1)','Nov vs CO1','Products','$/bbl'),
 'Gasoil Crack2':('GC2','Gasoil Dec crack vs Brent (QSCO2)','Dec vs CO2','Products','$/bbl'),
 'rbob crack 1':('RC1','RBOB-Brent crack (Dec Brent ref)','RB1 vs CO1','Products','$/bbl'),
 'rbob crack 2':('RC2','RBOB-Brent crack 2','RB2 vs CO2','Products','$/bbl'),
 'ho-go m1(Nov)':('HG1','HO-GO Nov (US vs Europe diesel arb)','Nov','Products','$/t'),
 'ho-go m2 (dec)':('HG2','HO-GO Dec','Dec','Products','$/t'),
}
def load():
    wb=openpyxl.load_workbook(SRC,data_only=True); out={}
    for sh,(k,*_) in META.items():
        ws=wb[sh]; rows=[r for r in ws.iter_rows(min_row=2,values_only=True) if r[0] is not None and isinstance(r[1],(int,float))]
        df=pd.DataFrame([(r[0],float(r[1]),(float(r[2]) if len(r)>2 and isinstance(r[2],(int,float)) else np.nan)) for r in rows],columns=['ts','px','vol']).sort_values('ts').drop_duplicates('ts').set_index('ts')
        out[k]=df
    return out
def session(h):  # Dubai time, bar stamp hour
    return 'Asia' if 2<=h<10 else ('Europe' if 10<=h<18 else 'US')
