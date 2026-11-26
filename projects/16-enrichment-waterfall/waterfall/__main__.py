"""python3 -m waterfall [--seed 7] : write the comparison report for the synthetic world."""
from __future__ import annotations

import argparse
from pathlib import Path

from .report import markdown
from .world import make_world


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrichment waterfall on a synthetic world")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("output/report.md"))
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown(make_world(args.seed)), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
