"""`python -m attribution`: run end to end and write reports/.

The optional Criteo outputs always go to the git-ignored output/ folder, never to reports/: the data is CC BY-NC-SA 4.0.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from . import report_criteo, report_world
from .analysis import Settings, analyse_world
from .criteo_run import run_criteo

PROJECT = Path(__file__).resolve().parent.parent
CRITEO_FILE = PROJECT / "data" / "raw" / "criteo_attribution_dataset.tsv.gz"
LOCAL_OUTPUT = PROJECT / "output"  # git-ignored
QUICK = Settings(users=20_000, boot=20, stability_seeds=2, sweep_worlds=4, sweep_users=10_000, holdout_reps=50)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m attribution", description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="report folder (default reports/; quick runs use output/)")
    parser.add_argument("--quick", action="store_true", help="small, fast run for a first look; numbers will differ")
    parser.add_argument("--seed", type=int, default=Settings.seed)
    parser.add_argument("--skip-criteo", action="store_true")
    parser.add_argument("--criteo-file", type=Path, default=CRITEO_FILE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = replace(QUICK if args.quick else Settings(), seed=args.seed)
    out = args.out or PROJECT / ("output" if args.quick else "reports")
    out.mkdir(parents=True, exist_ok=True)
    results = analyse_world(settings)
    (out / "report.md").write_text(report_world.build(results, out), encoding="utf-8")
    base = results.worlds["base"]
    print(f"Synthetic base world: {base.attribution.n_conversions:,} tracked conversions, "
          f"{base.truth.incremental_total:,} incremental of {base.truth.conversions_all_on:,}")
    print("Share error by world (lower is better):")
    print((100 * results.scores["base"][["share_error"]].rename(columns={"share_error": "base_%"})).assign(
        **{f"{w}_%": 100 * results.scores[w]["share_error"] for w in ("untargeted", "closer")}).round(1).to_string())
    print(f"SQL vs Python largest gap: {results.sql_gap:.4f} conversions")
    print(f"Wrote {out.name}/report.md")
    if args.skip_criteo or not args.criteo_file.is_file():
        print("Optional Criteo audit skipped (use fetch_data.py to download the file).")
        return 0
    n_boot = settings.boot
    criteo = run_criteo(args.criteo_file, n_boot)
    LOCAL_OUTPUT.mkdir(parents=True, exist_ok=True)
    (LOCAL_OUTPUT / "criteo_report.md").write_text(report_criteo.build(criteo, LOCAL_OUTPUT, n_boot), encoding="utf-8")
    print(f"Criteo: {criteo.prepared.n_conversions:,} click-path conversions, "
          f"{criteo.audit['conversion_paths_with_more_than_one_campaign']:,} multi-campaign. "
          f"Wrote {LOCAL_OUTPUT.name}/criteo_report.md (local only, do not commit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
