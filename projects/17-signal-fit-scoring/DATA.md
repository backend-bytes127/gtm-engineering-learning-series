# Data

Fetched **2026-11-26**. Run `python fetch_data.py` (main set) or `python fetch_data.py --candidates` (also the comparison set). Raw files go to `data/raw/`, which is git-ignored. No raw or row-level data is committed. `reports/` holds aggregates and charts, and `reports/model.json` holds model coefficients only.

## Main dataset: UCI Bank Marketing (with social and economic context)

| Item | Value |
|---|---|
| Source | https://archive.ics.uci.edu/dataset/222/bank+marketing |
| Owner / citation | Moro, S., Rita, P., & Cortez, P. (2014). Bank Marketing [Dataset]. UCI Machine Learning Repository. DOI 10.24432/C5K306 |
| Licence | Read on the source page: "This dataset is licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license." The page was read through a fetch tool that returns an extract, so re-check the wording before relying on it |
| Real or synthetic | **Real.** Phone campaigns of a Portuguese bank selling term deposits, May 2008 to November 2010. De-identified |
| Changes made here | A month is reconstructed from row order; fields are encoded; results are aggregated |

| File | Bytes | SHA-256 |
|---|---|---|
| Downloaded archive `bank+marketing.zip` (not kept by the script) | 1,023,843 | `e0bf5f5de5b846e2f18e9d90606637267d46dfa260e0f17bb12e605db5efbeb4` |
| `uci/bank-additional-full.csv` (41,188 rows, 21 columns) | 5,834,924 | `74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8` |

The script checks the CSV's hash. It does not check the archive's hash, because the archive can be re-zipped without the data changing.

### Columns

| Use | Columns |
|---|---|
| In the score | `job`, `education`, `default`, `housing`, `loan`, `poutcome`, `previous`, `pdays` |
| Outcome | `y` (subscribed or not) |
| Time | `month` (only to rebuild the calendar) plus row order |
| Excluded as leaks | `duration`, `campaign` |
| Excluded as not clearly known before calling | `month`, `day_of_week`, `contact` (as features) |
| Excluded by policy | `age`, `marital` |
| Excluded as market-wide clocks | `emp.var.rate`, `cons.price.idx`, `cons.conf.idx`, `euribor3m`, `nr.employed` |

### Leakage risks

- `duration`: the publisher's notes say it is not known before the call and should be dropped from a realistic model.
- `campaign`: "number of contacts performed during this campaign and for this client (numeric, includes last contact)". It is a final total.
- `month`, `day_of_week`, `contact` are described as belonging to the **last** contact of the campaign. Which contact is last is only known afterwards.
- The five economic indicators change over time and not between people on the same day. Their publication dates are not given.
- `poutcome`, `previous` and `pdays` are described as relating to earlier campaigns. This is taken on trust: there are no timestamps to prove it.
- `default`, `housing`, `loan`, `job`, `education`: the file does not say **when** they were recorded. If the bank updated them after a sale or a call, they leak.

### Known biases

- **Only people who were called are in the file.** Nothing is known about people the bank chose not to call, and how it chose changed over time.
- The win rate moves from 3% in May 2008 to above 50% in some 2010 months. Who was called changed, and so did the economy. The data cannot separate the two.
- The `year` is not a column. It is rebuilt from the publisher's statement that rows are in date order.
- `pdays = 999` means "not previously contacted" in the notes, yet some of those rows have `previous > 0`. They are treated as "contacted, date unknown".
- There is no client id, so one person could appear in both earlier and later months. This cannot be checked.
- There are a few fully duplicated rows (12 in the check done while exploring). They are kept, since two similar people can produce identical rows.
- No row-level calendar date, so outcome delay cannot be measured. The backtest **assumes** each month's outcomes are known before the next month starts.

### Privacy

There are no names, contact details or ids. These are still records about real people. They are used here to teach method, not to profile anyone, and rows are never republished.

### What this data cannot answer

Anything about B2B deals, pipeline stages, deal age, deal value, multiple contacts per account, intent signals with timestamps, or whether calling someone **caused** them to buy.

## Candidate datasets (checked, then limited or rejected)

### Maven Analytics CRM Sales Opportunities: fictitious

- Author's page: https://mavenanalytics.io/data-playground/crm-sales-opportunities says "B2B sales pipeline data from a fictitious company that sells computer hardware" and "License: Public Domain". The extract of that page gave 499 records, which does not match the 8,800 pipeline rows in the file downloaded. This is unresolved.
- Downloaded from a Kaggle mirror, https://www.kaggle.com/datasets/innocentmfa/crm-sales-opportunities, whose uploader labels it `apache-2.0`. The uploader is not the author.
- **Fictitious.** It has rep names, which are never printed or committed. A signal check is in the report.

| File | Bytes | SHA-256 |
|---|---|---|
| `sales_pipeline.csv` | 637,773 | `825ce8f6c32d4009548b468df3173d55a46fd73f2531f532c5459371dc52adf2` |
| `accounts.csv` | 4,670 | `e5242324768a563fc632cddfed49a29acbbf2892b8a3c6453cc9650de9ae0358` |
| `sales_teams.csv` | 1,284 | `aeff1272ebe196f5a27e3fc0578aa27abf48ed9ae461aa344fb95990e5ad8bd1` |
| `products.csv` (not used) | 171 | `7c1c8cbbdb6d4c286902e1985eeb529a36366d6a43f43cd4a93c4b1da2a6eb84` |
| `data_dictionary.csv` (not used) | 996 | `22b34e498d07e3d7f322afdbf81d70a5dc0a389792944e50ca2af86a3597f0af` |

### Not used

| Kaggle dataset | Licence in metadata | Why not used here |
|---|---|---|
| `olistbr/marketing-funnel-olist` | CC-BY-NC-SA-4.0 | Real B2B seller leads. The licence is non-commercial and share-alike, so this repository publishes no result from it and does not read it |
| `dataset066/crm-sales-opportunity-prediction-dataset` | CC-BY-SA-4.0 | Its own description says provenance "should be verified" before claiming it is real |
| `ayoubhannachi/b2b-lead-conversion-dataset-10k-records` | CC0-1.0 | No source stated, label about 50/50, and the description lists no dates |
| `shubhamm1729/car-dealership-crm-lead-scoring-and-sales-funnel` | not checked | Declares itself 100% synthetic |
| `derelictpanda/leadforge-lead-scoring-*` | not checked | Lead-scoring sets that a search result describes as generated |

A web search found no openly licensed set of real company opportunities with outcomes and dates. That is one search, not proof that none exists.
