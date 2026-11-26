-- Every source row gets exactly one bucket, so the buckets must add back to the file (see 05_checks.sql).
DROP TABLE IF EXISTS lines;
CREATE TABLE lines AS
SELECT r.*,
       CASE
         -- both sheets contain 1-9 December 2010; keep the second sheet's copy
         WHEN r.sheet_no = 1 AND r.ts >= (SELECT MIN(ts) FROM raw_lines WHERE sheet_no = 2) THEN 'overlap_duplicate'
         WHEN r.customer_id IS NULL THEN 'no_customer_id'
         -- merchandise codes start with five digits; the rest are postage, fees, manual adjustments and tests
         WHEN r.stock_code NOT GLOB '[0-9][0-9][0-9][0-9][0-9]*'
              AND r.stock_code NOT IN (SELECT stock_code FROM extra_codes) THEN 'non_merchandise_code'
         WHEN r.pence = 0 THEN 'zero_value'
         ELSE 'analysed'
       END AS bucket
FROM raw_lines AS r;
CREATE INDEX idx_lines ON lines (bucket, customer_id, ts);

DROP VIEW IF EXISTS analysed;
CREATE VIEW analysed AS
SELECT invoice, stock_code, qty, ts, pence, customer_id, country,
       CASE WHEN invoice NOT LIKE 'C%' AND qty > 0 AND pence > 0 THEN 1 ELSE 0 END AS is_sale
FROM lines
WHERE bucket = 'analysed';
