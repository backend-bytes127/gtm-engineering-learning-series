-- One row per comparison and customer. Window revenue is floored at zero: returns of an older order can make a
-- window negative, and negative "recurring revenue" would let GRR fall below 0%. The floor is reconciled.
DROP TABLE IF EXISTS customer_window;
CREATE TABLE customer_window AS
WITH summed AS (
  SELECT w.cmp, a.customer_id,
         SUM(CASE WHEN a.ts >= w.base_start AND a.ts < w.base_end THEN a.pence ELSE 0 END) AS base_net,
         SUM(CASE WHEN a.ts >= w.cur_start AND a.ts < w.cur_end THEN a.pence ELSE 0 END) AS cur_net
  FROM windows AS w
  JOIN analysed AS a
    ON (a.ts >= w.base_start AND a.ts < w.base_end) OR (a.ts >= w.cur_start AND a.ts < w.cur_end)
  GROUP BY w.cmp, a.customer_id
)
SELECT cmp, customer_id, base_net, cur_net, MAX(base_net, 0) AS start_pence, MAX(cur_net, 0) AS end_pence
FROM summed;

DROP TABLE IF EXISTS movements;
CREATE TABLE movements AS
SELECT v.cmp, v.customer_id, COALESCE(c.cohort, 'no sale on file') AS cohort, v.start_pence, v.end_pence,
       CASE WHEN v.start_pence = 0 AND v.end_pence > 0
             AND (c.first_sale IS NULL OR c.first_sale >= w.base_end) THEN v.end_pence ELSE 0 END AS new_pence,
       CASE WHEN v.start_pence = 0 AND v.end_pence > 0 AND c.first_sale < w.base_end THEN v.end_pence ELSE 0 END
         AS reactivation_pence,
       CASE WHEN v.start_pence > 0 AND v.end_pence > v.start_pence THEN v.end_pence - v.start_pence ELSE 0 END
         AS expansion_pence,
       CASE WHEN v.start_pence > 0 AND v.end_pence > 0 AND v.end_pence < v.start_pence
            THEN v.start_pence - v.end_pence ELSE 0 END AS contraction_pence,
       CASE WHEN v.start_pence > 0 AND v.end_pence = 0 THEN v.start_pence ELSE 0 END AS churn_pence
FROM customer_window AS v
JOIN windows AS w USING (cmp)
LEFT JOIN customers AS c USING (customer_id);
