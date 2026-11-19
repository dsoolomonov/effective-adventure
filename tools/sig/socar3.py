from q import q, cur
print("=== PrivateMarketInfo by month (fixture date)")
q("""SELECT FORMAT(FixtureDate,'yyyy-MM') m, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary
WHERE (QuantitySource='PrivateMarketInfo' OR CargoTypeSource='PrivateMarketInfo') AND FixtureDate>='2025-09-01' GROUP BY FORMAT(FixtureDate,'yyyy-MM') ORDER BY m DESC""", 15)
print("=== PrivateMarketInfo rows fixed 11-18 Sep (the Socar-received fixtures)")
q("""SELECT CAST(s.FixtureDate AS date) fixd, s.FixtureStatus fx, s.VesselName, s.VesselClass vc, s.FirstLoadPortName lp, CAST(s.FirstLoadPortSailingDate AS date) lay, s.LastDischargePortName dis, s.CargoType ct, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.Rate, s.RateType, s.Charterer ch, s.QuantitySource qs, s.CargoTypeSource cs
FROM dbo.uvS_VoyagesSummary s WHERE (s.QuantitySource='PrivateMarketInfo' OR s.CargoTypeSource='PrivateMarketInfo') AND s.FixtureDate>='2026-09-11' ORDER BY s.FixtureDate DESC""", 120)
print("=== Private vs public MarketInfo by class, Sep fixtures")
q("""SELECT VesselClass, QuantitySource, COUNT(*) n FROM dbo.uvS_VoyagesSummary WHERE FixtureDate>='2026-09-01' AND QuantitySource IN ('PrivateMarketInfo','MarketInfo') GROUP BY VesselClass, QuantitySource ORDER BY VesselClass, QuantitySource""", 10)
print("=== Charterers on private info Sep")
q("""SELECT Charterer, COUNT(*) n FROM dbo.uvS_VoyagesSummary WHERE FixtureDate>='2026-09-01' AND QuantitySource='PrivateMarketInfo' GROUP BY Charterer ORDER BY n DESC""", 30)
print("=== Socar-operated vessels")
q("""SELECT v.VesselName, v.IMO, v.VesselClassID vc, v.CommercialOperator op FROM dbo.uvs_Vessels v WHERE v.CommercialOperator LIKE '%socar%'""", 30)
print("=== Socar as charterer: all Sep/Oct incl future")
q("""SELECT CAST(s.FixtureDate AS date) fixd, s.FixtureStatus fx, CAST(s.FirstLoadPortSailingDate AS date) lay, s.VesselName, s.VesselClass vc, s.FirstLoadPortName lp, s.LastDischargePortName dis, s.CargoType ct, s.QuantityInBarrels/1e6 mb, s.Rate, s.RateType, s.Horizon h
FROM dbo.uvS_VoyagesSummary s WHERE s.Charterer='Socar' AND s.FirstLoadPortSailingDate>='2026-09-01' ORDER BY lay""", 30)
print("=== Aliaga (STAR) arrivals: cargoes by load port, sailed 1 Aug onward incl future")
q("""SELECT s.FirstLoadPortName lp, COUNT(*) n, SUM(s.QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary s WHERE s.LastDischargePortName='Aliaga' AND s.FirstLoadPortSailingDate>='2026-08-01' GROUP BY s.FirstLoadPortName ORDER BY mb DESC""", 20)
