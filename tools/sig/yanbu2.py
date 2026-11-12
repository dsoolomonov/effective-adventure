from q import q
print("=== all vessel classes present in Signal near Yanbu on latest day")
q("""SELECT d.VesselClass vc, d.VesselClassID vcid, COUNT(*) n FROM dbo.uvs_VesselDataPerDayEnhanced d
WHERE d.DayDate=(SELECT MAX(DayDate) FROM dbo.uvs_VesselDataPerDayEnhanced) AND (d.ClosestGeoAssetName LIKE '%Yanbu%' OR (d.AverageLatitude BETWEEN 22.5 AND 25.5 AND d.AverageLongitude BETWEEN 36 AND 39.5))
GROUP BY d.VesselClass, d.VesselClassID ORDER BY n DESC""", 20)
print("=== Suez/Afra at Yanbu latest day")
q("""SELECT v.VesselName, d.VesselClass vc, d.CommercialOperatorName op, d.LoadingState ls, d.Activity, d.Purpose, d.ActivityDurationInHours hrs, d.ClosestGeoAssetName loc, d.AISDestinationGeoAssetName dest, d.DaysSinceLastAIS dark, d.AverageDraught dr
FROM dbo.uvs_VesselDataPerDayEnhanced d LEFT JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE d.DayDate=(SELECT MAX(DayDate) FROM dbo.uvs_VesselDataPerDayEnhanced) AND d.VesselClassID IN (85,86) AND (d.ClosestGeoAssetName LIKE '%Yanbu%' OR (d.AverageLatitude BETWEEN 22.5 AND 25.5 AND d.AverageLongitude BETWEEN 36 AND 39.5))
ORDER BY d.VesselClass, d.Purpose""", 60)
print("=== daily presence Suez+Afra since Jun")
q("""SELECT DayDate, SUM(CASE WHEN VesselClassID=85 THEN 1 ELSE 0 END) suez, SUM(CASE WHEN VesselClassID=86 THEN 1 ELSE 0 END) afra, SUM(CASE WHEN Purpose='Load' THEN 1 ELSE 0 END) ld, SUM(CASE WHEN Activity='Operating' THEN 1 ELSE 0 END) oper, SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark
FROM dbo.uvs_VesselDataPerDayEnhanced WHERE VesselClassID IN (85,86) AND DayDate>='2026-06-01' AND (ClosestGeoAssetName LIKE '%Yanbu%' OR (AverageLatitude BETWEEN 22.5 AND 25.5 AND AverageLongitude BETWEEN 36 AND 39.5))
GROUP BY DayDate ORDER BY DayDate DESC""", 110)
print("=== Yanbu loadings by class + cargo group, monthly, Jun26-Sep26")
q("""SELECT DATEFROMPARTS(YEAR(FirstLoadPortSailingDate),MONTH(FirstLoadPortSailingDate),1) m, VesselClass vc, CargoGroup cg, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortName='Yanbu' AND FirstLoadPortSailingDate BETWEEN '2026-05-01' AND '2026-09-14'
GROUP BY DATEFROMPARTS(YEAR(FirstLoadPortSailingDate),MONTH(FirstLoadPortSailingDate),1), VesselClass, CargoGroup ORDER BY m, vc, cg""", 60)
print("=== Suez/Afra sailings from Yanbu since 25 Aug")
q("""SELECT VesselName, VesselClass vc, CommercialOperator op, FirstLoadPortSailingDate sail, QuantityInBarrels/1e3 kb, CargoGroup cg, CargoSubType, LastDischargePortName dp, LastDischargePortCountryName dc, Horizon
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (85,86) AND FirstLoadPortName='Yanbu' AND FirstLoadPortSailingDate BETWEEN '2026-08-25' AND '2026-09-14' ORDER BY sail""", 60)
