from q import q, cur
print("=== all tables/views")
rows = cur.execute("SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME").fetchall()
for r in rows: print(r[0], r[1], r[2])
print("=== columns mentioning fixture/charter/report/socar/receiver/consignee")
rows = cur.execute("""SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
WHERE COLUMN_NAME LIKE '%Fixture%' OR COLUMN_NAME LIKE '%Charter%' OR COLUMN_NAME LIKE '%Report%' OR COLUMN_NAME LIKE '%Socar%'
   OR COLUMN_NAME LIKE '%Receiver%' OR COLUMN_NAME LIKE '%Consignee%' OR COLUMN_NAME LIKE '%Source%' OR COLUMN_NAME LIKE '%Broker%' OR COLUMN_NAME LIKE '%Rate%' OR COLUMN_NAME LIKE '%Email%' OR COLUMN_NAME LIKE '%Lineup%'
ORDER BY TABLE_NAME, COLUMN_NAME""").fetchall()
for r in rows: print(r[0], r[1], r[2])
