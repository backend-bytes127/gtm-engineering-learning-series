"""`python -m pql` runs everything and writes reports/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pql import ingest, leakage, pipeline, plots, report, tracking_plan
from pql.config import BOOTSTRAP_REPS

PROJECT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pql", description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=PROJECT / "data" / "raw")
    parser.add_argument("--out-dir", type=Path, default=PROJECT / "reports")
    parser.add_argument("--bootstrap-reps", type=int, default=BOOTSTRAP_REPS)
    parser.add_argument("--skip-uci", action="store_true", help="do not run the PageValues leak test")
    args = parser.parse_args(argv)
    if args.bootstrap_reps < 20:
        parser.error("--bootstrap-reps must be at least 20")
    try:
        events = ingest.read_csv(ingest.verify_file(args.raw_dir, "retailrocket/events.csv"))
        uci = None
        if not args.skip_uci:
            uci_frame = ingest.read_csv(ingest.verify_file(args.raw_dir, "uci/online_shoppers_intention.csv"))
            uci = leakage.uci_page_value_test(uci_frame)
        results = pipeline.run(events, pipeline.RunConfig(bootstrap_reps=args.bootstrap_reps))
    except (ingest.DataError, tracking_plan.SchemaError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    plots.write_all(results, args.out_dir)
    (args.out_dir / "report.md").write_text(report.render(results, uci), encoding="utf-8")
    (args.out_dir / "metrics.json").write_text(json.dumps({**results, "uci": uci}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
