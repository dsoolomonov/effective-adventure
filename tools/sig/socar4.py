from q import q

print("=== Front Spey voyages")
q("""
SELECT s.VoyageID, CAST(s.FixtureDate AS datetime) fixd, s.FixtureStatus fx, s.FixtureIsHold hold,
       CAST(s.FirstLoadPortSailingDate AS date) lay, s.FirstLoadPortName lp, s.LastDischargePortName dis,
       s.CargoType ct, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.Quantity kt,
       s.Rate, s.RateType, s.Charterer ch, s.QuantitySource qs, s.CargoTypeSource cs,
       s.Horizon h, s.CommercialOperator op, s.UpdatedDate upd
FROM dbo.uvS_VoyagesSummary s
WHERE s.VesselName='Front Spey' AND s.FirstLoadPortSailingDate>='2026-06-01'
ORDER BY lay
""", 20)

print("=== Front Spey latest state")
q("""
SELECT VesselName, CAST(Timestamp AS datetime) ts, Latitude, Longitude, Draught, Speed, Destination, AreaNameLevel0, VesselState, LadenState
FROM dbo.uvs_LatestVesselState WHERE VesselName='Front Spey'
""", 5)
