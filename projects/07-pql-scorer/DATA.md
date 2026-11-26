# Data

Fetched 2026-11-26. `python fetch_data.py` downloads both sources into `data/raw/` (git-ignored) and verifies SHA-256. This is an engineering reading of licence statements, not legal advice. Raw rows and row-level derived data are never committed.

## 1. RetailRocket recommender system dataset (main source): REAL

| Item | Value |
|---|---|
| Source | <https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset> |
| Owner | `retailrocket` (Kaggle) |
| Licence | `CC-BY-NC-SA-4.0`, read from `kaggle datasets metadata -d retailrocket/ecommerce-dataset` (the `licenses` field). **Non-commercial, share-alike** |
| What the publisher says | Data "collected from a real-world ecommerce website"; "all values are hashed due to confidential issues"; published "to motivate researches in the field of recommender systems with implicit feedback" |
| Real or synthetic | Real behaviour, per the publisher. I cannot verify this independently. The signal behaves like real data: rare purchases, heavy-tailed activity, daily variation |
| Use here | Local, non-commercial learning and analysis. Aggregates and charts in `reports/` (and the figures quoted from them) are modified (aggregated, charted) material shared under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), with attribution to Retailrocket; the repository's MIT licence does not cover them (see `reports/LICENSE.md` and `NOTICE.md`) |

| File | Bytes | SHA-256 |
|---|---|---|
| `events.csv` (downloaded as a 33,971,694-byte zip) | 94,237,913 | `3745aa83238b1e6d44d8fda209807899f420084398f94ddf745f3cbcfecbf9e7` |

The dataset's item-property and category files were **not** downloaded.

**Columns used:** `timestamp` (Unix ms, UTC), `visitorid`, `event` (`view`, `addtocart`, `transaction`), `itemid`, `transactionid`. 2,756,101 rows from 3 May to 18 September 2015; 460 exact duplicates are removed.

**Personal data:** no direct identifiers. The visitor ids are pseudonymous records of real people's behaviour. They stay in `data/raw/` and never appear in reports.

**Biases and leakage risks**

- One unnamed shop, one period of 4.5 months, 2015. No claim of representativeness.
- A "visitor" is an id, probably cookie-based (the publisher does not say). Returning people can look new; the 14-day burn-in reduces this and cannot remove it.
- The history starts and ends abruptly. Visitors without a full 7-day label window are excluded; early ones are excluded by the burn-in.
- Bots are not labelled. One extreme visitor has 7,757 events.
- Transactions are one row per item. 656 training-period buyers have no recorded view-then-cart path.
- Any aggregate over a visitor's whole history leaks the future (tested in the report, section 7). Anything computed over the full file, such as item popularity or item conversion rate, would leak too and is not used.
- The item-property file, not used here, holds time-stamped weekly snapshots. Joining it without respecting time would be another leak.

## 2. UCI Online Shoppers Purchasing Intention (leak exhibit only)

| Item | Value |
|---|---|
| Source | <https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset> |
| Creators | C. Sakar, Yomi Kastro. DOI `10.24432/C5F88Q` |
| Licence | Read on the source page: "This dataset is licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license. This allows for the sharing and adaptation of the datasets for any purpose, provided that the appropriate credit is given." |
| Real or synthetic | Presented as real sessions; the UCI page says each of the 12,330 sessions belongs to a different user over a 1-year period |
| Personal data | No direct identifiers; one row per session of a real, unnamed person |

| File | Bytes | SHA-256 |
|---|---|---|
| `online_shoppers_intention.csv` (downloaded as a 1,072,219-byte zip) | 1,072,063 | `b3055ee355f59134d851d32641183cb4a8b45def7124d2f50442a042f358e0d9` |

**Columns used:** all 17 features and `Revenue` (label).

**`PageValues`:** UCI says the bounce-rate, exit-rate and page-value features are Google Analytics metrics, and that page value is the average value for a page a user visited before completing an e-commerce transaction. Google's [help article](https://support.google.com/analytics/answer/2695658) (Universal Analytics, read through a fetch tool that summarises pages) gives the formula as ecommerce revenue plus goal value, divided by unique pageviews. It is therefore built from outcomes. The dataset does not say what date range was used.

**Other risks:** behaviour columns are end-of-session totals, so they are not early signals. There is no date, only `Month`, with no January or April. The month split assumes the months follow calendar order within one year, which the file cannot confirm. The purchase rate in the test months (20.7%) differs from the overall rate (15.5%).

## Considered and not used

| Candidate | Reason (from `kaggle datasets metadata` / file listing) |
|---|---|
| REES46 `mkechinov/ecommerce-behavior-data-from-multi-category-store` | Licence field is `copyright-authors` (unclear); files of 5 GB and 8 GB |
| REES46 cosmetics shop and electronics store event histories | Licence field is `copyright-authors` (unclear) |
| `otto/recsys-dataset` (CC BY 4.0) | Training file 11 GB, over the limit; the 716 MB test file is one week, too short for this design. Not downloaded, contents not inspected |
| B2B free-trial or freemium product events | A short web and Kaggle search found no openly licensed set with outcomes. Not an exhaustive search |

## What this data cannot answer

- Anything about B2B accounts, buying committees, trials, seats, plans or revenue.
- Whether any outreach, nudge or discount **causes** purchases: no actions or experiment are recorded.
- Money: no usable order values, margins or costs are used. Every money figure in this project is an assumption.
- Who a visitor is, which channel brought them, or what they did elsewhere.
- Behaviour outside one 2015 season.
