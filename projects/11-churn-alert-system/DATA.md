# Data

## Dataset

| | |
|---|---|
| Name | Online Retail II |
| Source | https://archive.ics.uci.edu/dataset/502/online+retail+ii |
| Creator / host | Daqing Chen; UCI Machine Learning Repository |
| Citation | Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D |
| Licence, as quoted on the source page | "This dataset is licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license." |
| How it was read | The source page, through a page-fetch tool that returns the page text. Re-read the page before reusing |
| Real or synthetic | **Real.** The page says: "A real online retail transaction data set of two years." |
| Business | "UK-based and registered non-store online retail", "unique all-occasion gift-ware"; "Many customers of the company are wholesalers." |
| Period | 2009-12-01 07:45 to 2011-12-09 12:50 |
| Date fetched | 2026-11-26 |

**It is not SaaS or subscription contract data.** "Wholesalers" is a statement about many customers, not a per-customer flag, so
the analysis cannot separate business buyers from individuals.

Attribution and changes (CC BY 4.0): the source is credited above. This project removes a duplicated period, excludes rows without a
customer id and non-merchandise codes, converts money to integer pence, and publishes aggregates only.

## Files (all in the git-ignored `data/raw/`)

| File | Bytes | SHA-256 |
|---|---|---|
| online_retail_ii.zip | 45,622,418 | `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb` |
| online_retail_II.xlsx (inside the zip) | 45,622,278 | `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980` |

`python fetch_data.py` downloads and verifies both. `lines.parquet` is a local cache made by the first run.
The hashes were computed from the copy fetched on the date above; UCI does not publish them on that page.

## Columns used

`Invoice` (a leading C means cancellation), `StockCode`, `Quantity`, `InvoiceDate`, `Price` (GBP per unit), `Customer ID`,
`Country` (only "is United Kingdom"). `Description` is not read into the analysis frame.

## What the file contains that matters

- Two sheets, both holding 1-9 December 2010. The overlapping rows were compared and are identical; the first sheet's 22,523 rows are dropped.
- 235,287 rows (after removing the overlap) have no customer id, worth GBP 2,566,093 net. They cannot be retained or churned, so every
  retention figure describes identified customers only.
- 3,673 identified rows carry non-merchandise codes (postage, fees, manual adjustments, tests), net GBP -68,248. A code is merchandise
  only if it starts with five digits; some excluded codes may be real goods.
- 60 identified rows have zero value. 18 source rows have prices that are not whole pence; each line is rounded to the nearest penny
  (`round(quantity x price x 100)`), so "exact" means exact against these rounded lines.
- Some very large orders were cancelled minutes later. Netting handles them when both fall in one window. At least one sale is reversed by a
  manual-adjustment (`M`) line, which the main definition excludes; the sensitivity table shows the effect of counting `M`.
- Exact duplicate rows within a sheet are kept (they may be repeated invoice lines). The sensitivity table shows the effect of dropping them.

## Known biases and leakage risks

- **Left censoring:** customers seen in December 2009 may be years old. They form the "2009-12 or older" cohort. The annual comparison
  cannot tell new from reactivated customers for the base year.
- **Right censoring:** the file stops on 9 December 2011. December 2011 is left out of monthly and window figures; the code refuses to
  label a snapshot whose 90-day window is not fully observed.
- **One seller, two years:** each season appears about once or twice. Season cannot be separated from trend.
- **Leakage guards:** features read rows strictly before the snapshot; training snapshots are used only after their label window closed;
  cohort, lifetime totals and any whole-file aggregate are not features. The 90-day churn definition was chosen from gaps between purchase
  days before 2010-12-01 (85.5% of observed repeat gaps were 90 days or less; long gaps are under-counted because the period was short).
- **Survivorship in the scored population:** only repeat, recently active accounts are scored.

## What the data cannot answer

Why a customer stopped (price, stock, competitor, closure); whether outreach would change anything; contract renewals, MRR, seats or product
usage; margin; who owns the account; marketing or support contact; anything about rows without a customer id; whether the patterns hold
for any other company or any year after 2011.

## Privacy

Customer ids are pseudonymous numbers, but the records still describe real purchasing, and some customers may be individuals. Raw rows,
the parquet cache, the SQLite database, the alert queue and the alert history all stay local in git-ignored folders (`data/raw/`,
`output/`). Do not commit them or try to identify anyone. Committed reports hold aggregates only; some cohort cells describe a few hundred
accounts, and no account identifiers appear.

## Alternatives considered

A real subscription dataset with a clear licence was searched for on Kaggle (command-line search; not exhaustive). The SaaS
subscription sets inspected describe themselves as synthetic (one says it "was generated using ChatGPT and custom Python scripts", MIT;
another is titled "Synthetic"). KKBox data comes from a competition whose rules must be accepted, which was not done, and re-uploads were
not used. A synthetic SaaS table was rejected: a model would only recover whatever its generator planted.
