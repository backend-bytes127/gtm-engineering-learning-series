-- Each row is (name, left, right). Money is integer pence, so left must EQUAL right. No tolerance.
SELECT 'file rows = sum of bucket rows' AS name,
       (SELECT COUNT(*) FROM raw_lines) AS lhs,
       (SELECT SUM(n) FROM (SELECT COUNT(*) AS n FROM lines GROUP BY bucket)) AS rhs
UNION ALL
SELECT 'file value = sum of bucket value',
       (SELECT SUM(pence) FROM raw_lines),
       (SELECT SUM(v) FROM (SELECT SUM(pence) AS v FROM lines GROUP BY bucket))
UNION ALL
SELECT 'customer-month value = analysed line value',
       (SELECT SUM(net_pence) FROM customer_month), (SELECT SUM(pence) FROM analysed)
UNION ALL
SELECT 'waterfall rolls forward: ' || cmp,
       start_pence + new_pence + reactivation_pence + expansion_pence - contraction_pence - churn_pence, end_pence
FROM waterfall
UNION ALL
-- end and start are recomputed from lines, without using customer_window
SELECT 'window net + floor adjustment = waterfall end: ' || w.cmp,
       (SELECT SUM(pence) FROM analysed WHERE ts >= w.cur_start AND ts < w.cur_end)
       - (SELECT COALESCE(SUM(v), 0) FROM (SELECT SUM(pence) AS v FROM analysed
            WHERE ts >= w.cur_start AND ts < w.cur_end GROUP BY customer_id HAVING SUM(pence) < 0)),
       f.end_pence
FROM windows AS w JOIN waterfall AS f USING (cmp)
UNION ALL
SELECT 'window net + floor adjustment = waterfall start: ' || w.cmp,
       (SELECT SUM(pence) FROM analysed WHERE ts >= w.base_start AND ts < w.base_end)
       - (SELECT COALESCE(SUM(v), 0) FROM (SELECT SUM(pence) AS v FROM analysed
            WHERE ts >= w.base_start AND ts < w.base_end GROUP BY customer_id HAVING SUM(pence) < 0)),
       f.start_pence
FROM windows AS w JOIN waterfall AS f USING (cmp)
UNION ALL
SELECT 'cohort rows add to total start: ' || f.cmp, f.start_pence, SUM(c.start_pence)
FROM waterfall AS f JOIN cohort_retention AS c USING (cmp)
GROUP BY f.cmp
UNION ALL
SELECT 'cohort rows add to total churn: ' || f.cmp, f.churn_pence, SUM(c.churn_pence)
FROM waterfall AS f JOIN cohort_retention AS c USING (cmp)
GROUP BY f.cmp
UNION ALL
SELECT 'cohort rows add to total contraction: ' || f.cmp, f.contraction_pence, SUM(c.contraction_pence)
FROM waterfall AS f JOIN cohort_retention AS c USING (cmp)
GROUP BY f.cmp
UNION ALL
SELECT 'cohort rows add to total expansion: ' || f.cmp, f.expansion_pence, SUM(c.expansion_pence)
FROM waterfall AS f JOIN cohort_retention AS c USING (cmp)
GROUP BY f.cmp
UNION ALL
SELECT 'each customer has at most one movement type: ' || cmp,
       SUM((new_pence > 0) + (reactivation_pence > 0) + (expansion_pence > 0) + (contraction_pence > 0)
           + (churn_pence > 0) > 1), 0
FROM movements GROUP BY cmp
UNION ALL
SELECT 'cohort triangle buyers at month 0 = cohort size',
       (SELECT SUM(buyers) FROM cohort_month WHERE month_index = 0),
       (SELECT SUM(cohort_size) FROM cohort_month WHERE month_index = 0);
