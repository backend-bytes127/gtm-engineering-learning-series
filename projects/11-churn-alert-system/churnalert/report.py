"""Write reports/report.md and the PNG charts. Aggregates only: no account identifiers."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import charts
from .analysis import QueueResults, RetentionResults, RiskResults
from .config import CAPACITY, COOLDOWN_DAYS, GAP_EVIDENCE_END, HORIZON_DAYS, PLAN, QUEUE_POLICY
from .experiment import per_arm
from .queue import aggregate_queue
from .report_tables import backtest_rows, markdown_table, money, pct, retention_rows

BANNER = ("**Not SaaS contract data.** These are real invoices of one UK gift-ware seller with many wholesale customers, "
          "2009-2011 (UCI Online Retail II, CC BY 4.0). There are no subscriptions, renewals, MRR or cancellations of "
          "a contract. GRR and NRR here are repeat-purchase analogues, and churn is a definition we chose.")


def retention_section(r: RetentionResults) -> list[str]:
    annual = r.waterfall.set_index("cmp").loc["annual"]
    low_g, high_g = r.intervals["grr"]
    low_n, high_n = r.intervals["nrr"]
    buckets = r.buckets.assign(value_gbp=r.buckets["pence"].map(lambda p: money(p / 100)))[["bucket", "rows", "value_gbp"]]
    movement = ["start", "new", "reactivation", "expansion", "contraction", "churn", "end"]
    water = pd.DataFrame([{"comparison": w.cmp, **{m: money(getattr(w, f"{m}_pence") / 100) for m in movement}}
                          for w in r.waterfall.itertuples()])
    sens = r.sensitivity.assign(start_gbp=r.sensitivity["start_gbp"].map(money), grr=r.sensitivity["grr"].map(pct),
                                nrr=r.sensitivity["nrr"].map(pct))
    return [
        "## 1. Revenue retention", "",
        f"**Annual GRR {pct(annual.grr)}** (95% customer bootstrap {pct(low_g)} to {pct(high_g)}) and "
        f"**NRR {pct(annual.nrr)}** ({pct(low_n)} to {pct(high_n)}). Logo retention {pct(annual.logo_retention)} "
        f"({int(annual.retained_customers):,} of {int(annual.start_customers):,} base customers).", "",
        f"New customers added {money(annual.new_pence / 100)}, which is why total revenue moved from "
        f"{money(annual.start_pence / 100)} to {money(annual.end_pence / 100)} while NRR stayed below 100%.", "",
        "Definitions (per comparison; revenue = net merchandise value per customer per window, floored at zero):", "",
        "- base customer: revenue above zero in the base window.",
        "- churn: base customer with zero in the comparison window (all base revenue lost).",
        "- contraction / expansion: the fall or rise of a base customer still buying.",
        "- GRR = (start - churn - contraction) / start. NRR = (start - churn - contraction + expansion) / start.",
        "- new: nothing in the base window and first sale after it ended. Reactivation: nothing in the base window, "
        "first sale before it ended. Neither enters GRR or NRR.",
        "- The annual reactivation line is close to zero by construction: the file has no history before the base year.", "",
        markdown_table(water), "", markdown_table(retention_rows(r.waterfall, ["cmp"])), "",
        "![Annual waterfall](waterfall.png)", "", "![Retention by comparison](retention.png)", "",
        f"The right-hand chart is the trap: month-on-month 'GRR' averages {pct(r.trap['naive_grr'].mean())} and "
        f"{pct(r.trap['lapsed_share'].mean())} of buyers 'churn' every month, because wholesale buyers do not order monthly.", "",
        "### By acquisition cohort (annual)", "",
        markdown_table(retention_rows(r.cohorts[r.cohorts["cmp"] == "annual"], ["cohort"])), "",
        "**Read with care.** A cohort acquired during the base year has only part of a year in its base and a full year in "
        "the comparison, which pushes its NRR up. Later cohorts above 100% are mostly this, not proof they grow faster. "
        "The 2009-12 cohort also contains customers of unknown age, because the file starts that month. "
        "Quarterly comparisons by cohort (same months a year apart):", "",
        markdown_table(retention_rows(r.cohorts[r.cohorts["cmp"] != "annual"], ["cmp", "cohort"])), "",
        "A quarterly cohort is still part-way through its first order cycle if it was acquired inside the base quarter.", "",
        "![Monthly cohort activity](cohorts.png)", "",
        "### How much do cleaning choices matter?", "", markdown_table(sens), "",
        "### Reconciliation (SQL, integer pence, no tolerance)", "",
        "Where every source row went:", "", markdown_table(buckets), "",
        f"**{int(r.checks['ok'].sum())} of {len(r.checks)} checks balance exactly.** The run stops with an error if one fails. "
        "Check families: file rows and value equal the buckets; customer-month equals lines; each waterfall rolls forward; "
        "start and end are recomputed from lines plus the zero-floor adjustment; cohorts add to totals; one movement type "
        "per customer; cohort triangle month 0 equals cohort size.", ""]


def risk_section(k: RiskResults) -> list[str]:
    boot = k.bootstrap.assign(**{c: k.bootstrap[c].map(lambda v: f"{v:.3f}") for c in ("estimate", "low", "high")})
    versus = k.bootstrap_overdue[k.bootstrap_overdue["who"] == "difference"]
    versus = versus.assign(**{c: versus[c].map(lambda v: f"{v:+.3f}") for c in ("estimate", "low", "high")})
    revenue = k.bootstrap_revenue
    revenue = revenue[(revenue["who"] == "difference") & revenue["metric"].isin(["precision", "ev_value_captured"])]
    revenue = revenue.assign(**{c: revenue[c].map(lambda v: f"{v:+.3f}") for c in ("estimate", "low", "high")})
    segments = k.segments.assign(churn_rate=k.segments["churn_rate"].map(pct),
                                 mean_predicted=k.segments["mean_predicted"].map(pct),
                                 auc_model=k.segments["auc_model"].map(lambda v: f"{v:.3f}"),
                                 auc_baseline=k.segments["auc_baseline"].map(lambda v: f"{v:.3f}"))
    replay = k.cooldown.assign(alert_precision=k.cooldown["alert_precision"].map(pct),
                               unique_precision=k.cooldown["unique_precision"].map(pct),
                               churned_value_flagged_gbp=k.cooldown["churned_value_flagged_gbp"].map(money))
    weeks = {name: part["as_of"].nunique() for name, part in (("dev", k.dev_scored), ("test", k.test_scored))}
    rows = k.test_scored[k.test_scored["model"] == k.chosen]
    return [
        "## 2. Churn-risk model", "",
        f"- **Scored:** at 00:00 on a Monday, accounts with at least 2 purchase days in the previous 180 days and a purchase "
        f"in the last {HORIZON_DAYS} days. Features use only earlier rows, all from a fixed 180-day lookback.",
        f"- **Churned:** no purchase day in the next {HORIZON_DAYS} days. It is not proof the account is gone. "
        f"Why {HORIZON_DAYS}: of {k.gaps['gaps']:,} gaps between purchase days before {GAP_EVIDENCE_END}, "
        f"{pct(k.gaps['within_horizon'])} were {HORIZON_DAYS} days or less (long gaps are under-counted in so short a period).",
        f"- **Training at each origin:** snapshots every {PLAN.train_step_days} days from {PLAN.first_train}, only those "
        f"whose {HORIZON_DAYS}-day label had closed by the origin.",
        f"- **Development:** {weeks['dev']} weekly origins {PLAN.dev_start} to {PLAN.dev_end}. **Test:** {weeks['test']} "
        f"weekly origins {PLAN.test_start} to {PLAN.test_end} ({len(rows):,} account-weeks, "
        f"{rows['customer_id'].nunique():,} accounts).",
        f"- **Model choice rule:** lowest development log loss among the fitted models: **{k.chosen}**.", "",
        "### Development weeks", "", markdown_table(backtest_rows(k.dev)), "",
        "### Test weeks", "", markdown_table(backtest_rows(k.test)), "",
        f"`precision`, `recall` and `value captured` are at {CAPACITY} accounts a week, averaged over weeks, ranking by risk. "
        "`ev_` columns rank by risk x trailing 180-day revenue. For `base_rate` that is the same as ranking by revenue alone, "
        "the 'call the biggest accounts' baseline. `value captured` is the share of the trailing revenue of "
        "all that week's churners that sits in the top list. Ties are scored as random order.", "",
        "![Precision by week](precision_by_week.png)", "",
        "### Uncertainty (test, whole customers resampled; `difference` is paired, model minus recency rule)", "",
        markdown_table(boot), "",
        "Against the stronger rule at capacity, `overdue_rule` (days silent / the account's usual gap), model minus rule:", "",
        markdown_table(versus.drop(columns="who")), "",
        "An interval that includes zero means this test cannot separate the two on that metric.", "",
        "Against `base_rate`, model minus baseline. For `precision` the baseline is random picking. For `ev_value_captured` "
        "the model ranks by risk x value and the baseline ranks by revenue alone:", "",
        markdown_table(revenue.drop(columns="who")), "",
        "These intervals cover which customers were sampled, **not** which season. All test outcomes fall between "
        "June and early December 2011, and weekly windows overlap: there is little more than one independent 90-day period.", "",
        "### Calibration", "", "![Calibration](calibration.png)", "",
        "Expected calibration error: " + ", ".join(f"{name.lower()} {value:.3f}" for name, value in k.ece.items()) +
        ". The base churn rate moves with the season, and with under two years of data no model here can learn that. "
        "Treat the score as a ranking, not as a probability to put in a forecast.", "",
        "### Where the model helps and where it does not (test)", "", markdown_table(segments), "",
        f"### The queue as operated: an alerted account rests for {COOLDOWN_DAYS} days (test weeks)", "",
        markdown_table(replay), "",
        "Ranking by risk alone the model flags mostly small accounts, so a simple rule can touch more churned revenue. "
        "`churned value flagged` is the trailing 180-day revenue of flagged accounts that then churned, each counted once. "
        "It is **not** money saved: nothing shows that outreach would have kept any of them.", ""]


def action_section(k: RiskResults, q: QueueResults) -> list[str]:
    table = aggregate_queue(q.queue)
    table = table.assign(mean_score=table["mean_score"].map(lambda v: f"{v:.2f}"),
                         net_180d_gbp=table["net_180d_gbp"].map(money),
                         value_at_risk_gbp=table["value_at_risk_gbp"].map(money))
    ev = k.test.set_index("model").loc[k.chosen]
    base = float(ev["base_rate"])
    replay = k.cooldown.set_index(["model", "policy"])
    replay_unique = replay.loc[(k.chosen, "risk"), "unique_accounts"]
    revenue_only = float(k.test.set_index("model").loc["base_rate", "ev_value_captured"])
    against = k.bootstrap_revenue
    diff = against[(against["who"] == "difference") & (against["metric"] == "ev_value_captured")].iloc[0]
    plan = []
    for reduction in (0.05, 0.10):
        if base > reduction:
            plan.append(f"{per_arm(base, reduction):,} accounts per arm for a {100 * reduction:.0f}-point fall")
    return [
        "## 3. What customer success should do this week", "",
        f"Queue as of {q.as_of} (model trained on {q.training_rows:,} closed account-snapshots). "
        f"{q.coverage['eligible']:,} of {q.coverage['buyers_180']:,} buyers in the last 180 days are eligible; they hold "
        f"{pct(q.coverage['eligible_value_share'])} of that period's net revenue. One-time and already-lapsed buyers are "
        "outside this queue and need a separate onboarding or win-back motion.", "",
        f"The ranked list ({len(q.queue)} accounts, capacity {CAPACITY} is an **assumption**) is ranked by **{QUEUE_POLICY}** "
        "and written to a local, git-ignored CSV. **Nothing is sent.** By primary reason:", "",
        markdown_table(table), "",
        "`value_at_risk` is churn score x trailing 180-day net revenue: a priority number, not a forecast loss.", "",
        f"**Default: rank by churn score.** On test weeks its precision at capacity was {pct(ev['precision'])}, against "
        f"{pct(base)} for all eligible accounts. The alternative, ranking by risk x value (`policy=\"value\"`), had "
        f"{pct(ev['ev_precision'])} precision. **This is lower than the {pct(base)} you would expect from picking eligible "
        "accounts at random.** The ranking trades hit rate for revenue.", "",
        f"What each order buys: the share of churners' trailing revenue in the top list was {pct(ev['value_captured'])} "
        f"ranked by risk, {pct(ev['ev_value_captured'])} ranked by risk x value and {pct(revenue_only)} ranked by revenue "
        f"alone. Risk x value minus revenue alone is {100 * diff.estimate:+.1f} points (95% {100 * diff.low:+.1f} to "
        f"{100 * diff.high:+.1f}). So the default gives up revenue coverage, including against revenue alone, to get a list "
        "in which more of the alerts are real. No interval was computed between the two model-based orders.", "",
        "This queue is dated 10 December, after the seasonal peak, and its 90-day window (December to March) is the "
        "post-peak lull. There is no outcome for it in the data, so it has not been evaluated.", "",
        "### Prove that outreach works", "",
        "The model predicts who stops buying, not who can be persuaded. Randomly hold out part of the flagged accounts. "
        f"At a {pct(base)} control churn rate (80% power, 5% two-sided) you need about " + " or ".join(plan) +
        f". Count each account once. Replaying {k.test_scored['as_of'].nunique()} test weeks, the default queue reached "
        f"{int(replay_unique):,} different accounts, to be split between both arms, so even a 10-point effect would take "
        "longer than that to test, and the season would change during the experiment. Flagged accounts churn more often than "
        "the average, so size again from the control arm you expect.", ""]


def write(out: Path, r: RetentionResults, k: RiskResults, q: QueueResults) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    charts.waterfall_chart(r.waterfall.set_index("cmp").loc["annual"], out / "waterfall.png")
    charts.cohort_heatmap(r.triangle, out / "cohorts.png")
    charts.retention_chart(r.waterfall, r.trap, out / "retention.png")
    charts.calibration_chart(k.calibration, out / "calibration.png")
    charts.precision_chart(k.weeks, CAPACITY, out / "precision_by_week.png")
    lines = ["# Revenue retention and churn-risk report", "", BANNER, "",
             "Source: Chen, D. (2012). Online Retail II. UCI Machine Learning Repository, "
             "https://doi.org/10.24432/C5CG6D (CC BY 4.0). Aggregated and cleaned here as described in DATA.md.", "",
             *retention_section(r), *risk_section(k), *action_section(k, q)]
    path = out / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
