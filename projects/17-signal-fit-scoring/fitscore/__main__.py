"""python -m fitscore                  run the backtest and write reports/
python -m fitscore score --input new.csv --output scored.csv"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .data import load_bank
from .pipeline import headline, run
from .score import TIER_MODES, score_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fitscore", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=config.UCI_CSV)
    parser.add_argument("--raw", type=Path, default=config.RAW)
    parser.add_argument("--out", type=Path, default=config.REPORTS)
    parser.add_argument("--config", type=Path, default=config.DEFAULT_CONFIG)
    parser.add_argument("--bootstrap", type=int, default=1000)
    commands = parser.add_subparsers(dest="command")
    score = commands.add_parser("score", help="score new rows with the saved model")
    score.add_argument("--input", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--model", type=Path, default=config.REPORTS / "model.json")
    score.add_argument("--tier-mode", choices=TIER_MODES, default="batch", help="batch: rank inside this file (default)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "score":
            result = score_file(args.input, args.output, args.model, args.tier_mode)
            print(f"scored {len(result)} rows -> {args.output}")
            print(result["tier"].value_counts().sort_index().to_string())
        else:
            if args.bootstrap < 1:
                raise ValueError("--bootstrap must be at least 1")
            results = run(load_bank(args.data), config.load_config(args.config), args.out, args.raw, reps=args.bootstrap)
            print(headline(results))
            print(f"report: {args.out / 'report.md'}")
    except (FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
