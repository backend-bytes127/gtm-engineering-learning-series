-- Transition counts for the first-order Markov chain, over converting AND non-converting journeys.
WITH steps AS (
    SELECT '(start)' AS from_state, channel AS to_state FROM sequenced WHERE position = 1
    UNION ALL
    SELECT a.channel, b.channel
    FROM sequenced AS a
    JOIN sequenced AS b ON b.journey_id = a.journey_id AND b.position = a.position + 1
    UNION ALL
    SELECT channel, CASE WHEN converted = 1 THEN '(conversion)' ELSE '(null)' END
    FROM sequenced WHERE position = path_length
)
SELECT from_state, to_state, COUNT(*) AS n
FROM steps
GROUP BY from_state, to_state
ORDER BY from_state, to_state;
