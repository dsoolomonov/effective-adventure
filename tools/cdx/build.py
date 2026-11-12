import json
from datetime import date
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.axis import DateAxis
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

p = json.load(open('/home/ubuntu/pstk/lcd.json'))
WIN = '2026-02-01'
HDR = PatternFill('solid', fgColor='1F3A5F'); HF = Font(bold=True, color='FFFFFF')
thin = Side(style='thin', color='BFBFBF'); BOX = Border(top=thin, bottom=thin, left=thin, right=thin)
FIG = {'northsea': 'Fig 4 North Sea', 'med': 'Fig 5 Med BS Caspian'}
FULL = {'northsea': 'North Sea daily 2016-', 'med': 'Med daily 2016-'}

wb = Workbook()
rd = wb.active; rd.title = 'README'
rows = [
    ['Crude differentials vs Dated Brent strips, $/bbl'],
    [f"Source: Platts (S&P Global Commodity Insights) daily close assessments (bate c), pulled {p['generated_at']} UTC; latest assessment {p['as_of']}."],
    ['Same data as the Barrel Terminal Crude Differentials tab (Fig. 4 / Fig. 5 and tables). Values are Platts prints, not modelled.'],
    ['Fig sheets = chart window (from 1 Feb 2026). Daily sheets = full history from Jan 2016. Blank cell = no Platts assessment that day.'],
    ['Summary: w/w, m/m, 3m, y/y vs last print on or before 7/30/91/365 days earlier; 5y avg = mean of same date in 2021-2025; 5y %ile = rank of last print in trailing 5y.'],
    [],
    ['Chart', 'Grade', 'Platts symbol', 'Platts description / basis', 'On in tab chart by default'],
]
for r in rows: rd.append(r)
for c in rd[7]: c.fill, c.font = HDR, HF
for g in p['groups']:
    for gr in g['grades']:
        rd.append([g['short'], gr['name'], gr['symbol'], gr['desc'], 'yes' if gr['default'] else 'no (extra grade)'])
rd['A1'].font = Font(bold=True, size=14)
for col, w in zip('ABCDE', (26, 18, 14, 60, 24)): rd.column_dimensions[col].width = w

def grid(ws, g, start):
    ds = sorted({d for gr in g['grades'] for d in gr['dates'] if d >= start})
    look = [dict(zip(gr['dates'], gr['values'])) for gr in g['grades']]
    ws.append(['Date'] + [f"{gr['name']}" for gr in g['grades']])
    ws.append(['Platts symbol'] + [gr['symbol'] for gr in g['grades']])
    for c in ws[1]: c.fill, c.font, c.alignment = HDR, HF, Alignment(horizontal='center', wrap_text=True)
    for c in ws[2]: c.font = Font(italic=True, color='595959')
    for d in ds:
        ws.append([date.fromisoformat(d)] + [lk.get(d) for lk in look])
    for r in ws.iter_rows(min_row=3, min_col=1, max_col=1):
        r[0].number_format = 'dd-mmm-yy'
    for r in ws.iter_rows(min_row=3, min_col=2):
        for c in r: c.number_format = '0.00'
    ws.column_dimensions['A'].width = 12
    for i in range(2, len(g['grades']) + 2): ws.column_dimensions[get_column_letter(i)].width = 15
    ws.freeze_panes = 'B3'
    return len(ds)

for g in p['groups']:
    ws = wb.create_sheet(FIG[g['id']])
    n = grid(ws, g, WIN)
    ch = LineChart(); ch.title = g['name'] + ', $/bbl'; ch.y_axis.title = '$/bbl'
    ch.height, ch.width = 13, 30
    ch.x_axis = DateAxis(crossAx=100); ch.x_axis.number_format = 'mmm-yy'; ch.x_axis.majorTimeUnit = 'months'; ch.x_axis.majorUnit = 1; ch.x_axis.baseTimeUnit = 'days'; ch.x_axis.tickLblPos = 'low'
    ch.y_axis.crossAx = 500; ch.x_axis.title = None
    ch.x_axis.delete = False; ch.y_axis.delete = False
    defaults = [i for i, gr in enumerate(g['grades']) if gr['default']]
    for i in defaults:
        ch.add_data(Reference(ws, min_col=i + 2, min_row=1, max_row=n + 2 if False else n + 2), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=3, max_row=n + 2))
    for s in ch.series:
        s.smooth = False; s.graphicalProperties.line.width = 19050
    ws.add_chart(ch, f"{get_column_letter(len(g['grades']) + 3)}3")
    wf = wb.create_sheet(FULL[g['id']])
    grid(wf, g, '2000-01-01')

# chart series include row 2 (symbol) as data otherwise; rebuild refs to skip it
for g in p['groups']:
    ws = wb[FIG[g['id']]]; ch = ws._charts[0]; n = ws.max_row
    ch.series.clear()
    from openpyxl.chart import Series
    for i, gr in enumerate(g['grades']):
        if not gr['default']: continue
        s = Series(Reference(ws, min_col=i + 2, min_row=3, max_row=n), title=gr['name'])
        s.smooth = False; s.graphicalProperties.line.width = 19050
        ch.series.append(s)
    ch.set_categories(Reference(ws, min_col=1, min_row=3, max_row=n))

sm = wb.create_sheet('Summary', 1)
cols = [('Last', 'value'), ('Date', 'date'), ('d/d', 'dod'), ('w/w', 'wow'), ('m/m', 'mom'), ('3m', 'm3'), ('y/y', 'yoy'),
        ('30d avg', 'avg30'), ('YTD avg', 'ytd_avg'), ('52w high', 'hi52'), ('52w high date', 'hi52_date'),
        ('52w low', 'lo52'), ('52w low date', 'lo52_date'), ('5y avg', 'avg5y'), ('vs 5y', 'vs5y'), ('5y yrs', 'five_n'),
        ('5y %ile', 'pctile5y'), ('Status', 'status')]
for g in p['groups']:
    sm.append([g['name'] + ', $/bbl']); sm.cell(sm.max_row, 1).font = Font(bold=True, size=12)
    sm.append(['Grade', 'Symbol', 'Basis'] + [c for c, _ in cols])
    for c in sm[sm.max_row]: c.fill, c.font, c.alignment = HDR, HF, Alignment(horizontal='center')
    for gr in g['grades']:
        st = gr['stats']
        row = [gr['name'], gr['symbol'], gr['desc']]
        for _, k in cols:
            v = st.get(k)
            if k in ('date', 'hi52_date', 'lo52_date') and v: v = date.fromisoformat(v)
            row.append(round(v, 4) if isinstance(v, float) else v)
        sm.append(row)
        r = sm.max_row
        for j, (_, k) in enumerate(cols, start=4):
            c = sm.cell(r, j); c.border = BOX
            if k in ('date', 'hi52_date', 'lo52_date'): c.number_format = 'dd-mmm-yy'
            elif k in ('five_n', 'pctile5y', 'status'): pass
            elif k in ('dod', 'wow', 'mom', 'm3', 'yoy', 'vs5y'): c.number_format = '+0.00;-0.00;0.00'
            else: c.number_format = '0.00'
        if not gr['default']:
            for c in sm[r][:3]: c.font = Font(color='808080')
    sm.append([])
sm.column_dimensions['A'].width = 16; sm.column_dimensions['B'].width = 10; sm.column_dimensions['C'].width = 52
for i in range(4, 4 + len(cols)): sm.column_dimensions[get_column_letter(i)].width = 11
sm.freeze_panes = 'D1'
out = f"/home/ubuntu/cdx/crude_diffs_platts_{p['as_of']}.xlsx"
wb.save(out); print(out)
