"""Copy only what the container needs into a clean folder, laid out as the Dockerfile expects.

Usage: python3 deploy/stage.py /path/to/empty/folder
Then deploy that folder (its root holds Dockerfile and railway.json).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", ".pytest_cache")


def stage(dest: Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"{dest} is not empty")
    p2, p4 = "projects/02-contact-list-merge", "projects/04-contact-cleaning-app"
    shutil.copytree(REPO / p2 / "pipeline", dest / p2 / "pipeline", ignore=IGNORE)
    shutil.copytree(REPO / p2 / "sample-data", dest / p2 / "sample-data", ignore=IGNORE)
    shutil.copytree(REPO / p4 / "contactapp", dest / p4 / "contactapp", ignore=IGNORE)
    shutil.copy(REPO / p4 / "requirements-prod.txt", dest / p4 / "requirements-prod.txt")
    shutil.copy(REPO / p4 / "Dockerfile", dest / "Dockerfile")  # Railway looks for a Dockerfile at the root
    config = (REPO / p4 / "railway.json").read_text().replace(f"{p4}/Dockerfile", "Dockerfile")
    (dest / "railway.json").write_text(config)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    stage(Path(sys.argv[1]))
    print(f"Staged into {sys.argv[1]}")
