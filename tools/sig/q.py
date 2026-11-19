import pyodbc, sys
cs = ("DRIVER={ODBC Driver 18 for SQL Server};SERVER=s-vsrv-dw1.public.ae13c07752d5.database.windows.net,3342;"
      "DATABASE=DW_Socar;UID=Socar_user;PWD={zB&-5Q@xw%UgY6};Encrypt=yes;TrustServerCertificate=yes;ApplicationIntent=ReadOnly;")
conn = pyodbc.connect(cs, autocommit=True, timeout=120)
cur = conn.cursor()

def cols(v):
    rows = cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=? ORDER BY ORDINAL_POSITION", v).fetchall()
    print(f"\n== {v} ({len(rows)} cols)")
    print(", ".join(f"{c}:{t}" for c, t in rows))

def q(sql, n=5):
    print("\n--", sql[:160])
    try:
        cur.execute(sql)
        names = [d[0] for d in cur.description]
        for r in cur.fetchmany(n):
            print({k: (str(v)[:40] if v is not None else None) for k, v in zip(names, r)})
    except Exception as e:
        print("ERR", e)

if __name__ == "__main__":
    for a in sys.argv[1:]:
        if a.startswith("cols:"): cols(a[5:])
        else: q(a)
