-- first_sale decides acquisition cohort. Customers seen in December 2009 may be years old: the file starts there.
DROP TABLE IF EXISTS customers;
CREATE TABLE customers AS
SELECT customer_id,
       MIN(ts) AS first_sale,
       CASE
         WHEN MIN(ts) < '2010-01-01' THEN '2009-12 or older'
         WHEN MIN(ts) < '2010-04-01' THEN '2010 Jan-Mar'
         WHEN MIN(ts) < '2010-07-01' THEN '2010 Apr-Jun'
         WHEN MIN(ts) < '2010-10-01' THEN '2010 Jul-Sep'
         WHEN MIN(ts) < '2010-12-01' THEN '2010 Oct-Nov'
         ELSE 'after Nov 2010'
       END AS cohort
FROM analysed
WHERE is_sale = 1
GROUP BY customer_id;

DROP TABLE IF EXISTS customer_month;
CREATE TABLE customer_month AS
SELECT customer_id, SUBSTR(ts, 1, 7) AS month, SUM(pence) AS net_pence, MAX(is_sale) AS bought
FROM analysed
GROUP BY customer_id, SUBSTR(ts, 1, 7);

-- Monthly cohort triangle. month_index 0 is the first purchase month.
DROP TABLE IF EXISTS cohort_month;
CREATE TABLE cohort_month AS
WITH dated AS (
  SELECT m.customer_id, m.month, m.net_pence, m.bought, SUBSTR(c.first_sale, 1, 7) AS cohort_month
  FROM customer_month AS m JOIN customers AS c USING (customer_id)
),
sized AS (
  SELECT SUBSTR(first_sale, 1, 7) AS cohort_month, COUNT(*) AS cohort_size FROM customers GROUP BY 1
)
SELECT d.cohort_month,
       (CAST(SUBSTR(d.month, 1, 4) AS INTEGER) - CAST(SUBSTR(d.cohort_month, 1, 4) AS INTEGER)) * 12
         + CAST(SUBSTR(d.month, 6, 2) AS INTEGER) - CAST(SUBSTR(d.cohort_month, 6, 2) AS INTEGER) AS month_index,
       s.cohort_size,
       SUM(d.bought) AS buyers,
       SUM(d.net_pence) AS net_pence
FROM dated AS d JOIN sized AS s USING (cohort_month)
WHERE d.month >= d.cohort_month AND d.month <= (SELECT last_full_month FROM params)
GROUP BY d.cohort_month, month_index, s.cohort_size;
