import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from q import cur

def q(sql, n=200):
    print("\n--", sql[:200])
    try:
        cur.execute(sql)
        names = [d[0] for d in cur.description]
        print(" | ".join(names))
        for r in cur.fetchmany(n):
            print(" | ".join(str(v)[:60] if v is not None else "-" for v in r))
    except Exception as e:
        print("ERR", e)

if __name__ == "__main__":
    for a in sys.argv[1:]:
        q(a)
