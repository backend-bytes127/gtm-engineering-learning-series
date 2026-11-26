-- GRR = (start - churn - contraction) / start.  NRR = (start - churn - contraction + expansion) / start.
-- Both are over customers with revenue in the base window. New and reactivated revenue is never in either.
DROP VIEW IF EXISTS waterfall;
CREATE VIEW waterfall AS
SELECT cmp,
       SUM(start_pence) AS start_pence, SUM(new_pence) AS new_pence, SUM(reactivation_pence) AS reactivation_pence,
       SUM(expansion_pence) AS expansion_pence, SUM(contraction_pence) AS contraction_pence,
       SUM(churn_pence) AS churn_pence, SUM(end_pence) AS end_pence,
       SUM(start_pence > 0) AS start_customers,
       SUM(start_pence > 0 AND end_pence > 0) AS retained_customers
FROM movements
GROUP BY cmp;

DROP VIEW IF EXISTS cohort_retention;
CREATE VIEW cohort_retention AS
SELECT cmp, cohort,
       SUM(start_pence > 0) AS start_customers,
       SUM(start_pence > 0 AND end_pence > 0) AS retained_customers,
       SUM(start_pence) AS start_pence, SUM(churn_pence) AS churn_pence,
       SUM(contraction_pence) AS contraction_pence, SUM(expansion_pence) AS expansion_pence
FROM movements
WHERE start_pence > 0
GROUP BY cmp, cohort;
