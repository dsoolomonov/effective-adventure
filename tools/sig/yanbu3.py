from q import q
print("=== data currency")
q("SELECT MAX(DayDate) mx FROM dbo.uvs_VesselDataPerDayEnhanced", 1)
q("SELECT MAX(LastMovementDateTimeUTC) mx FROM dbo.uvs_LatestVesselState", 1)
print("=== departures: voyages with Yanbu load and sailing date in last 3 days (incl. modelled)")
q("""SELECT VesselName, VesselClass vc, CommercialOperator op, Charterer ch, FirstLoadPortArrivalDate arr, FirstLoadPortSailingDate sail, FirstLoadGeoAssetName ga, QuantityInBarrels/1e3 kb, CargoGroup cg, CargoSubType, LastDischargePortName dp, LastDischargePortCountryName dc, Horizon, FixtureStatus fs, LatestReceivedAIS ais
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortName='Yanbu' AND FirstLoadPortSailingDate BETWEEN DATEADD(day,-3,'2026-09-15') AND DATEADD(day,2,'2026-09-15') ORDER BY sail""", 40)
print("=== vessels that were at Yanbu 2 days ago but have left the box now (latest state)")
q("""SELECT v.VesselName, d.VesselClass vc, d.LoadingState ls_then, s.VesselVoyageStatus st_now, s.LastMovementDateTimeUTC t, ROUND(s.Latitude,2) la, ROUND(s.Longitude,2) lo, s.Speed, s.Draught, s.AISDestination dest, s.AISDestinationETA eta
FROM dbo.uvs_VesselDataPerDayEnhanced d JOIN dbo.uvs_LatestVesselState s ON s.IMO=d.IMO LEFT JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE d.DayDate=DATEADD(day,-2,'2026-09-15') AND d.VesselClassID IN (84,85,86)
AND (d.ClosestGeoAssetName LIKE '%Yanbu%' OR (d.AverageLatitude BETWEEN 22.5 AND 25.5 AND d.AverageLongitude BETWEEN 36 AND 39.5))
AND NOT (s.Latitude BETWEEN 22.5 AND 25.5 AND s.Longitude BETWEEN 36 AND 39.5) ORDER BY t DESC""", 40)
print("=== state changes at Yanbu: vessels present today with status vs 2 days ago")
q("""SELECT v.VesselName, a.VesselClass vc, b.LoadingState ls_2d, a.LoadingState ls_now, b.AverageDraught dr_2d, a.AverageDraught dr_now, b.Purpose p_2d, a.Purpose p_now, a.Activity act_now, a.ClosestGeoAssetName loc, a.AISDestinationGeoAssetName dest, a.DaysSinceLastAIS dark
FROM dbo.uvs_VesselDataPerDayEnhanced a LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate=DATEADD(day,-2,a.DayDate) LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='2026-09-15' AND a.VesselClassID IN (84,85,86)
AND (a.ClosestGeoAssetName LIKE '%Yanbu%' OR (a.AverageLatitude BETWEEN 22.5 AND 25.5 AND a.AverageLongitude BETWEEN 36 AND 39.5))
ORDER BY a.VesselClass, a.Purpose""", 40)
print("=== latest state for key names")
q("""SELECT v.VesselName, s.LastMovementDateTimeUTC t, ROUND(s.Latitude,2) la, ROUND(s.Longitude,2) lo, s.Speed, s.Draught, s.VesselVoyageStatus st, s.AISDestination dest, s.AISDestinationETA eta
FROM dbo.uvs_LatestVesselState s JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO
WHERE v.VesselName IN ('Roberta B','Hala Light','Bluebell','Sikinos I','C. Brave','Kenya B','Plata West','Front Silkeborg','SFL Albany','Alatau','Aspen','Spetses Lady','Erotokritos','HTM Titan','Sami Bay','Safeen Baroness','Asp Titan','Plata Glory') ORDER BY v.VesselName""", 30)
