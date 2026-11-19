from q import q
q("""SELECT DayDate, COUNT(*) vlcc, SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden, SUM(CASE WHEN Purpose='Load' THEN 1 ELSE 0 END) ld, SUM(CASE WHEN Activity='Operating' THEN 1 ELSE 0 END) oper, SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark
FROM dbo.uvs_VesselDataPerDayEnhanced WHERE VesselClassID=84 AND DayDate>='2026-06-01' AND (ClosestGeoAssetName LIKE '%Yanbu%' OR (AverageLatitude BETWEEN 22.5 AND 25.5 AND AverageLongitude BETWEEN 36 AND 39.5))
GROUP BY DayDate ORDER BY DayDate DESC""", 110)
