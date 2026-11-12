import pdfplumber, re, json

PDF = "/home/ubuntu/attachments/33c614a8-5e4f-4145-b330-123d7c36fc64/1789050256652-202609_LEM_chartpack.pdf"

def lines_of(page):
    ws = page.extract_words(x_tolerance=1)
    rows = {}
    for w in ws:
        key = round(w['top'] / 3)
        rows.setdefault(key, []).append(w)
    out = []
    for k in sorted(rows):
        toks = sorted(rows[k], key=lambda w: w['x0'])
        # merge tokens with small gap
        merged = []
        for t in toks:
            if merged and t['x0'] - merged[-1]['x1'] < 2.5:
                merged[-1] = {'text': merged[-1]['text'] + t['text'], 'x0': merged[-1]['x0'], 'x1': t['x1']}
            else:
                merged.append({'text': t['text'], 'x0': t['x0'], 'x1': t['x1']})
        out.append(merged)
    return out

pdf = pdfplumber.open(PDF)
for i, page in enumerate(pdf.pages):
    ls = lines_of(page)
    if not ls:
        continue
    print(f"===== page {i+1} =====")
    for line in ls:
        print(" | ".join(t['text'] for t in line))
