"""``python -m hub``: rebuild the workflow files, run the offline tour and write ``reports/``."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from hub import report, workflows
from hub.churn import as_of_from_name, parse_queue
from hub.messages import churn_digest
from hub.simulate import run_tour

ROOT = Path(__file__).resolve().parent.parent
FIXED_NOW = 1_800_000_000  # a fixed clock keeps the offline report identical between runs


def latest_queue(inbox: Path) -> Path:
    files = sorted(inbox.glob("alert_queue_*.csv"))
    if not files:
        raise SystemExit(f"no alert_queue_YYYY-MM-DD.csv in {inbox.name}/")
    return files[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hub", description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT, help="folder that receives workflows/ and reports/")
    args = parser.parse_args(argv)
    written = workflows.write_all(args.out / "workflows")
    queue = latest_queue(ROOT / "samples" / "inbox")
    accounts, as_of = parse_queue(queue.read_text(encoding="utf-8")), as_of_from_name(queue.name)
    digest_day = date.fromisoformat(as_of)
    preview = churn_digest(accounts, as_of, digest_day)
    observations = run_tour(FIXED_NOW)
    report.write(observations, accounts, as_of, digest_day, args.out / "reports")
    (args.out / "reports" / "churn_digest_preview.json").write_text(
        json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    failed = [o.step.name for o in observations if not o.matched]
    print(f"workflows written: {len(written)}")
    print(f"offline tour: {len(observations) - len(failed)} of {len(observations)} steps as expected")
    for name in failed:
        print(f"  unexpected result: {name}")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
