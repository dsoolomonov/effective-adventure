from q import q, cur
# columns of voyages summary
rows = cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='uvS_VoyagesSummary' ORDER BY ORDINAL_POSITION").fetchall()
print([r[0] for r in rows])
print("=== Aframax/Suez clean-ish cargo types Europe->US since 1 Aug")
q("""SELECT s.CargoType, s.CargoSubType, COUNT(*) n, SUM(s.QuantityInBarrels)/1e3 kb
FROM dbo.uvS_VoyagesSummary s
WHERE s.FirstLoadPortSailingDate>='2026-08-01' AND s.LastDischargePortCountryName='United States'
AND s.FirstLoadPortCountryName IN ('Netherlands','Belgium','United Kingdom','France','Germany','Spain','Italy','Portugal','Norway','Sweden','Denmark','Finland','Poland','Lithuania','Latvia','Estonia','Ireland','Greece','Turkey')
GROUP BY s.CargoType, s.CargoSubType ORDER BY n DESC""", 40)
print("=== detail: Europe -> US East Coast, clean cargoes, sailing since 20 Aug (incl. Current/Future)")
q("""SELECT CAST(s.FirstLoadPortSailingDate AS date) sail, v.VesselName, s.VesselClassID vc, s.FirstLoadPortName lp, s.CargoType ct, s.CargoSubType grade, s.QuantityInBarrels/1e3 kb, s.LastDischargePortName dp, CAST(s.LastDischargePortArrivalDate AS date) arr, s.Horizon h, s.ChartererName ch, s.FixtureStatus fx
FROM dbo.uvS_VoyagesSummary s JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO
WHERE s.FirstLoadPortSailingDate>='2026-08-20' AND s.LastDischargePortCountryName='United States'
AND s.FirstLoadPortCountryName IN ('Netherlands','Belgium','United Kingdom','France','Germany','Spain','Italy','Portugal','Norway','Sweden','Denmark','Finland','Poland','Lithuania','Latvia','Estonia','Ireland','Greece','Turkey')
AND (s.CargoType LIKE '%Clean%' OR s.CargoType LIKE '%CPP%' OR s.CargoSubType LIKE '%Gasoline%' OR s.CargoSubType LIKE '%Naphtha%' OR s.CargoSubType LIKE '%Blend%' OR s.CargoSubType LIKE '%Reform%' OR s.CargoSubType LIKE '%Alkyl%')
ORDER BY sail DESC""", 60)
