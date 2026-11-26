"""Write the results as markdown. Aggregates only: no visitor or item id ever reaches a report."""

from __future__ import annotations


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def pct(value: float, places: int = 2) -> str:
    return f"{100 * value:.{places}f}%"


def _ci(pair: tuple[float, float], places: int = 3) -> str:
    return f"[{pair[0]:.{places}f}, {pair[1]:.{places}f}]"


def data_section(r: dict) -> str:
    t = r["tracking"]
    violations = ", ".join(f"{k}: {v:,}" for k, v in t["violations"].items()) or "none"
    cohort = [[k.replace("_", " "), f"{v:,}"] for k, v in r["cohort"].items()]
    splits = [[n, f"{s['visitors']:,}", f"{s['buyers']:,}", pct(s["rate"], 3)] for n, s in r["splits"].items()]
    timing = [[f"{x['cutoff_minutes']:,}", pct(x["share_already_bought"], 1)] for x in r["buyer_timing"]]
    return "\n\n".join(
        [
            "## 1. Tracking-plan validation",
            f"Rows in: {t['rows_in']:,}. Rows kept: {t['rows_clean']:,}. Violations: {violations}.",
            "## 2. Cohort and splits",
            table(["count", "visitors"], cohort),
            table(["split", "visitors", "later buyers", "rate"], splits),
            "## 3. How early is early enough?",
            "Minutes after a visitor's first event, and the share of eventual buyers who had already bought by then.",
            table(["minutes", "buyers already bought"], timing),
            "![buyer timing](buyer_timing.png)",
        ]
    )


def behaviour_section(r: dict) -> str:
    sens = [
        [
            f"{x['cutoff_minutes']:,}", f"{x['bought_before_cutoff']:,}", f"{x['later_buyers']:,}", pct(x["validation_rate"], 3),
            f"{x['average_precision']:.4f}", f"{x['roc_auc']:.3f}", f"{x['lift_at_1pct']:.1f}x", pct(x["recall_at_1pct"], 1),
        ]
        for x in r["sensitivity"]
    ]
    miles = [
        [
            m["milestone"], pct(m["reach"]), pct(m["buy_rate_reached"]), pct(m["buy_rate_not_reached"]),
            f"{m['lift_over_base']:.1f}x", pct(m["share_of_later_buyers"], 1),
        ]
        for m in r["milestones"]
    ]
    steps = [
        [f["step"], f"{f['visitors']:,}", pct(f["from_previous"]), f"{f['median_minutes']:.1f}"]
        if f["step"] != "purchased_without_that_path"
        else [f["step"], f"{f['visitors']:,}", "-", "-"]
        for f in r["funnel"]
    ]
    return "\n\n".join(
        [
            "## 4. Cut-off sensitivity (logistic regression, validation period only)",
            "Each row is a different population, so average precision is not directly comparable between rows.",
            table(["cut-off min", "bought before", "later buyers", "base rate", "AP", "ROC AUC", "lift top 1%", "recall top 1%"], sens),
            "## 5. Activation milestones (training period)",
            table(["milestone", "reach", "buy rate if reached", "if not", "lift", "share of later buyers"], miles),
            "![milestones](milestones.png)",
            "## 6. Funnel (ALL new visitors in the training period, including fast buyers; first 7 days)",
            table(["step", "visitors", "from previous step", "median minutes from previous"], steps),
            "The last row counts buyers with no recorded view-then-cart path: a tracking gap or a route the events do not show.",
        ]
    )


def leak_section(r: dict, uci: dict | None) -> str:
    window = [[x["features"], f"{x['average_precision']:.4f}", f"{x['roc_auc']:.3f}"] for x in r["leak_window"]]
    parts = [
        "## 7. Leak test 1: looking past the cut-off (validation)",
        table(["features", "AP", "ROC AUC"], window),
        "The second row is wrong on purpose. No feature in it mentions a purchase.",
    ]
    if uci:
        rows = [[x["variant"], f"{x['average_precision']:.3f}", f"{x['roc_auc']:.3f}"] for x in uci["variants"]]
        parts += [
            "## 8. Leak test 2: UCI Online Shoppers `PageValues`",
            f"{uci['sessions']:,} sessions, purchase rate {pct(uci['buy_rate'], 1)}. Train Feb-Sep ({uci['train_sessions']:,}), "
            f"test Oct-Dec ({uci['test_sessions']:,}, purchase rate {pct(uci['test_buy_rate'], 1)}).",
            f"`PageValues` is above zero for {pct(uci['pv_positive_among_buyers'], 1)} of buying sessions and "
            f"{pct(uci['pv_positive_among_non_buyers'], 1)} of the others. Purchase rate when above zero: "
            f"{pct(uci['buy_rate_pv_positive'], 1)}; when zero: {pct(uci['buy_rate_pv_zero'], 1)}.",
            table(["columns used", "AP", "ROC AUC"], rows),
        ]
    return "\n\n".join(parts)


def model_section(r: dict) -> str:
    s = r["selection"]
    val = [
        [x["scorer"], f"{x['average_precision']:.4f}", f"{x['roc_auc']:.3f}", pct(x["precision_at_capacity"])]
        for x in s["validation_table"]
    ]
    test = [
        [
            x["scorer"], f"{x['average_precision']:.4f}", _ci(x["intervals"]["average_precision"], 4), f"{x['roc_auc']:.3f}",
            _ci(x["intervals"]["average_precision_minus_points_rule"], 4),
            _ci(x["intervals"]["precision_at_capacity_minus_points_rule"], 4),
        ]
        for x in r["test"]["ranking"]
    ]
    cap = [
        [pct(x["fraction"], 1), x["scorer"], f"{x['contacted']:,}", pct(x["precision"]), pct(x["recall"], 1), f"{x['lift']:.1f}x"]
        for x in r["test"]["capacity"]
    ]
    prob = [
        [n, f"{m['brier']:.6f}", f"{m['log_loss']:.5f}", pct(m["mean_predicted"], 3), pct(m["observed_rate"], 3)]
        for n, m in r["test"]["probability"].items()
    ]
    cal = [
        [f"{c['n']:,}", pct(c["predicted"], 3), pct(c["observed"], 3), f"{pct(c['low'], 3)} to {pct(c['high'], 3)}"]
        for c in r["test"]["calibration"]
    ]
    imp = [[x["feature"], f"{x['ap_drop']:.4f}"] for x in r["importance"][:6]]
    return "\n\n".join(
        [
            "## 9. Model choice (validation only)",
            table(["scorer", "AP", "ROC AUC", "precision top 1%"], val),
            f"Boosting minus logistic, AP, paired 95% interval: {_ci(s['boosting_minus_logistic_ap_interval'], 4)}. "
            f"Chosen: **{s['chosen']}** (boosting is chosen only if that interval is above zero).",
            "## 10. Held-out test period",
            table(["scorer", "AP", "AP 95%", "ROC AUC", "AP minus points rule 95%", "precision@1% minus points rule 95%"], test),
            "### At fixed capacity",
            table(["acted on", "scorer", "visitors", "precision", "recall", "lift"], cap),
            "![gains](gains.png)",
            "### Probability quality",
            table(["probability", "Brier", "log loss", "mean predicted", "observed"], prob),
            f"Platt calibrator fitted on validation: slope {r['calibrator']['slope']:.3f}, intercept {r['calibrator']['intercept']:.3f}.",
            table(["visitors", "mean predicted", "observed", "95% interval"], cal),
            "![calibration](calibration.png)",
            "### What the model leans on (validation, permutation: drop in AP)",
            table(["feature", "AP drop"], imp),
        ]
    )


def routing_section(r: dict) -> str:
    parts = [
        "## 11. Routing under daily capacity (test period)",
        f"Thresholds on the calibrated probability, set on validation ({r['policy']['validation_per_day']:,.0f} eligible visitors "
        f"per day): A at {pct(r['policy']['thresholds'][0])} or higher, B at {pct(r['policy']['thresholds'][1])} or higher.",
    ]
    for name, block in r["test"]["routing"].items():
        rows = [
            [
                t["tier"], f"{t['visitors']:,}", f"{t['per_day']:.0f}", f"{t['buyers']:,}", pct(t["buy_rate"]),
                f"{pct(t['buy_rate_low'])} to {pct(t['buy_rate_high'])}", pct(t["share_of_buyers"], 1),
            ]
            for t in block["tiers"]
        ]
        parts += [
            f"### Policy: {name}",
            table(["tier", "visitors", "per day", "later buyers", "buy rate", "95% interval", "share of buyers"], rows),
            f"Visitors who met a tier threshold when that tier was already full: {block['visitors_hitting_a_full_tier']:,}.",
        ]
    seg = [
        [
            s["segment"], pct(s["share_of_visitors"], 1), f"{s['later_buyers']:,}", pct(s["share_of_buyers"], 1), pct(s["buy_rate"], 3),
            pct(s["buyers_above_lowest_threshold"], 1),
        ]
        for s in r["test"]["segments"]
    ]
    weeks = [
        [
            w["week"], f"{w['visitors']:,}", f"{w['buyers']:,}", pct(w["observed_rate"], 3), pct(w["mean_predicted"], 3),
            f"{w['average_precision']:.4f}",
        ]
        for w in r["weekly"]
    ]
    parts += [
        "## 12. Where the model loses",
        table(["segment", "share of visitors", "later buyers", "share of buyers", "buy rate", "their buyers above B threshold"], seg),
        "### By week",
        table(["week", "visitors", "buyers", "observed", "predicted", "AP"], weeks),
        "![weekly](weekly.png)",
    ]
    return "\n\n".join(parts)


def experiment_text(r: dict) -> str:
    e = r["experiment"]
    parts = [
        "## 13. A/B test design: does the routed action cause purchases?",
        "**Everything above is prediction. None of it shows that any action changes behaviour.** Two-sided test, alpha 0.05, "
        "power 0.80, purchase within 7 days of the cut-off. Baseline and volume are the observed test-period values per tier. "
        "The lifts are hypothetical effect sizes to plan for, not results.",
    ]
    for d in e["designs"]:
        rows = [
            [
                pct(x["relative_lift"], 0), f"{pct(x['treated_share'], 0)} / {pct(1 - x['treated_share'], 0)}", pct(x["treated_rate"]),
                f"{x['n_treated']:,}", f"{x['n_control']:,}", f"{x['enrol_days']:,}", f"{x['days_to_readout']:,}",
            ]
            for x in d["rows"]
        ]
        parts += [
            f"### {d['tier']}: baseline {pct(d['baseline'])}, {d['per_day']:.0f} visitors per day",
            table(["relative lift", "treated / holdout", "treated rate", "n treated", "n holdout", "enrol days", "days to readout"], rows),
        ]
        if "break_even_lift" in d:
            cost = e["assumptions"]["cost_per_action"][d["tier"]]
            parts.append(
                f"ASSUMED money (not in the data): cost {cost:.2f} per action and margin {e['assumptions']['margin_per_order']:.2f} "
                f"per order give a break-even relative lift of {pct(d['break_even_lift'], 0)}."
            )
    if e["simulation_check"]:
        c = e["simulation_check"]
        parts.append(
            f"Formula check by simulation ({c['tier']}, {pct(c['relative_lift'], 0)} lift, 50/50, 20,000 runs): "
            f"power {c['power']:.3f} against a target of 0.800."
        )
    return "\n\n".join(parts)


def render(results: dict, uci: dict | None) -> str:
    header = (
        "# PQL scorer: run report\n\nGenerated by `python -m pql`. Source: RetailRocket events (real, anonymised web-shop behaviour, "
        "2015, by Retailrocket, https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset; CC BY-NC-SA 4.0, "
        "https://creativecommons.org/licenses/by-nc-sa/4.0/; aggregated and charted, so modified. This report and its charts are "
        "shared under the same terms and are not covered by the repository's MIT licence)"
        + (" and UCI Online Shoppers (CC BY 4.0)." if uci else ".")
        + " It is a shop, not a B2B product trial."
    )
    sections = [header, data_section(results), behaviour_section(results), leak_section(results, uci)]
    sections += [model_section(results), routing_section(results), experiment_text(results)]
    return "\n\n".join(sections) + "\n"
