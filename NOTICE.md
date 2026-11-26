# Notices: third-party data and licences

The [MIT licence](LICENSE) covers the code and original text in this repository. It does **not** cover results derived from datasets under
CC BY-NC-SA 4.0, listed in section 1. Results derived from CC BY 4.0 sources keep their attribution duty (section 2). No raw rows from
the datasets below are committed. No creator listed here endorses this repository. This file is an engineering reading of licence
statements, not legal advice.

## 1. CC BY-NC-SA 4.0 material (excluded from the MIT licence)

**Retailrocket recommender system dataset**

- Creator: Retailrocket
- Dataset: <https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset>
- Licence deed: <https://creativecommons.org/licenses/by-nc-sa/4.0/> (Attribution-NonCommercial-ShareAlike 4.0 International)
- Changes: the material here is **modified**. Events were filtered, aggregated, modelled and charted.

The following are shared under CC BY-NC-SA 4.0 (non-commercial, share-alike), not under MIT:

| Location | What is covered |
|---|---|
| `projects/07-pql-scorer/reports/` | Everything in the folder: report, metrics and charts. The parts that report the UCI Online Shoppers dataset remain CC BY 4.0 |
| `projects/07-pql-scorer/README.md` and `DATA.md` | The result figures and observations derived from the dataset |
| `projects/07-pql-scorer/docs/pql-scorer.png`, `pql-scorer.excalidraw`, `make_diagram.py` | The result figures shown in the diagram |
| `projects/07-pql-scorer/docs/process.md` and any other file in the project | Any result figure derived from the dataset |

The program code of project 07 stays under MIT.

## 2. CC BY 4.0 sources

Licence deed for all rows: <https://creativecommons.org/licenses/by/4.0/>. In each case the material is **modified**: cleaned or filtered
where the project's `DATA.md` says so, then aggregated, modelled and charted.

| Source | Creators and citation | Used in |
|---|---|---|
| [Online Shoppers Purchasing Intention Dataset](https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset), UCI Machine Learning Repository, <https://doi.org/10.24432/C5F88Q> | C. Sakar and Yomi Kastro | `projects/07-pql-scorer` (second leak test) |
| [Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii), UCI Machine Learning Repository, <https://doi.org/10.24432/C5CG6D> | Daqing Chen (2012) | `projects/11-churn-alert-system` |
| [Bank Marketing](https://archive.ics.uci.edu/dataset/222/bank+marketing), UCI Machine Learning Repository, <https://doi.org/10.24432/C5K306> | S. Moro, P. Rita and P. Cortez (2014) | `projects/17-signal-fit-scoring` |

## 3. Statistics quoted in the industry guides

The guides in `docs/industry-guides/` quote and sum statistics from **Eurostat** and add their own assumptions; the estimates and market
calculations are not Eurostat's. Reuse terms: <https://ec.europa.eu/eurostat/help/copyright-notice>. Each guide lists its datasets and
other sources. Third-party sources cited there keep their own terms.
