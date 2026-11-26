"""The attribution code must not be able to see the planted truth."""
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "attribution"
BLIND = ["allocate", "channels", "journeys", "heuristics", "markov", "shapley", "methods", "uncertainty", "decisions", "sqllayer",
         "criteo", "criteo_run", "holdout"]
TRUTH_MODULES = ("world", "world_events", "truth", "scenario", "evaluate", "analysis")


def test_blind_modules_do_not_import_the_world_or_the_truth():
    for module in BLIND:
        imports = [line for line in (PACKAGE / f"{module}.py").read_text().splitlines() if line.startswith(("from ", "import "))]
        for line in imports:
            assert not any(line.startswith(f"from .{name} ") for name in TRUTH_MODULES), f"{module}: {line}"
