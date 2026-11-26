-- Point-in-time rule: a touch counts only if it happened strictly before the journey ended
-- (the conversion, or the end of observation) and inside the lookback window.
-- DISTINCT removes exact duplicate events.
CREATE VIEW eligible AS
SELECT DISTINCT t.journey_id, t.ts, t.channel, j.converted, j.end_ts
FROM raw_touches AS t
JOIN journeys AS j USING (journey_id)
CROSS JOIN settings AS s
WHERE t.ts < j.end_ts
  AND t.ts >= j.end_ts - s.lookback_seconds;

CREATE VIEW sequenced AS
SELECT journey_id, ts, channel, converted, end_ts,
       ROW_NUMBER() OVER (PARTITION BY journey_id ORDER BY ts, channel) AS position,
       COUNT(*)     OVER (PARTITION BY journey_id) AS path_length,
       MAX(ts)      OVER (PARTITION BY journey_id) AS newest_ts
FROM eligible;
