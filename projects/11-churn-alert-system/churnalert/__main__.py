"""python -m churnalert: SQL retention, rolling-origin backtest, this week's queue, report."""
from __future__ import annotations

import argparse
from pathlib import Path

from . import analysis, backtest, data, features, report, sqldb
from .config import BOOTSTRAP_REPS

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="churnalert", description=__doc__)
    parser.add_argument("--xlsx", type=Path, default=ROOT / "data" / "raw" / "online_retail_II.xlsx")
    parser.add_argument("--reports", type=Path, default=ROOT / "reports", help="aggregates only; safe to commit")
    parser.add_argument("--local", type=Path, default=ROOT / "output", help="account-level files; git-ignored, never commit")
    parser.add_argument("--reps", type=int, default=BOOTSTRAP_REPS, help="customer bootstrap replicates")
    args = parser.parse_args(argv)
    if args.reps < 1:
        parser.error("--reps must be at least 1")
    try:
        raw = data.load(args.xlsx, args.xlsx.with_name("lines.parquet"))
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    args.local.mkdir(parents=True, exist_ok=True)
    con = sqldb.build(raw, str(args.local / "retention.sqlite"))
    retained = analysis.run_retention(raw, con, args.reps)
    snapshots = backtest.Snapshots(features.prepare(sqldb.analysed_lines(con)), {})
    risk = analysis.run_risk(snapshots, reps=args.reps)
    queue = analysis.run_queue(snapshots, risk.chosen, args.local)
    path = report.write(args.reports, retained, risk, queue)
    con.close()
    annual = retained.waterfall.set_index("cmp").loc["annual"]
    test = risk.test.set_index("model")
    print(f"reconciliation: {int(retained.checks['ok'].sum())}/{len(retained.checks)} checks balance exactly")
    print(f"annual GRR {annual.grr:.1%}  NRR {annual.nrr:.1%}  logo retention {annual.logo_retention:.1%}")
    print(f"chosen on development weeks: {risk.chosen}")
    for name in (risk.chosen, "recency_rule", "overdue_rule", "base_rate"):
        row = test.loc[name]
        print(f"test {name:<13} AUC {row.auc:.3f}  Brier {row.brier:.3f}  precision@25 {row.precision:.1%}  "
              f"value-ranked precision {row.ev_precision:.1%}  value captured {row.ev_value_captured:.1%}")
    print(f"report: {path}")
    print(f"alert queue (local only, nothing sent): {queue.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
