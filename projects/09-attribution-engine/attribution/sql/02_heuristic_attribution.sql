-- Fractional credit per channel for the five positional rules.
-- The Python layer does the same split in integer units; a test holds the two together.
WITH weighted AS (
    SELECT q.journey_id, q.channel, q.position, q.path_length,
           CASE WHEN q.position = 1 THEN 1.0 ELSE 0.0 END AS first_w,
           CASE WHEN q.position = q.path_length THEN 1.0 ELSE 0.0 END AS last_w,
           1.0 / q.path_length AS linear_w,
           -- age is measured from the newest touch so that a long gap cannot underflow to zero
           decay_weight(q.newest_ts - q.ts, s.half_life_seconds) AS decay_w,
           CASE
               WHEN q.path_length = 1 THEN 1.0
               WHEN q.path_length = 2 THEN 0.5
               WHEN q.position IN (1, q.path_length) THEN 0.4
               ELSE 0.2 / (q.path_length - 2)
           END AS u_w
    FROM sequenced AS q
    CROSS JOIN settings AS s
    WHERE q.converted = 1
),
shared AS (
    SELECT channel, first_w, last_w, linear_w, u_w,
           decay_w / SUM(decay_w) OVER (PARTITION BY journey_id) AS decay_share
    FROM weighted
)
SELECT channel,
       SUM(first_w)     AS first_touch,
       SUM(last_w)      AS last_touch,
       SUM(linear_w)    AS linear,
       SUM(decay_share) AS time_decay,
       SUM(u_w)         AS u_shaped
FROM shared
GROUP BY channel
ORDER BY channel;
