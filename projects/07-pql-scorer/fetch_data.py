"""Download the two public datasets into data/raw/ and verify their SHA-256.

RetailRocket needs the `kaggle` command-line tool, already configured by you. This script never reads credentials.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from pql.ingest import EXPECTED_SHA256, DataError, verify_file

RAW = Path(__file__).resolve().parent / "data" / "raw"
UCI_URL = "https://archive.ics.uci.edu/static/public/468/online+shoppers+purchasing+intention+dataset.zip"


def extract_member(archive: Path, member: str, directory: Path) -> None:
    """Extract exactly one named file, so nothing else in an archive is ever written."""
    with zipfile.ZipFile(archive) as bundle, bundle.open(member) as source, (directory / member).open("wb") as target:
        shutil.copyfileobj(source, target)


def fetch_uci(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "online_shoppers.zip"
    with urllib.request.urlopen(UCI_URL, timeout=120) as response, archive.open("wb") as target:  # noqa: S310
        shutil.copyfileobj(response, target)
    extract_member(archive, "online_shoppers_intention.csv", directory)


def fetch_retailrocket(directory: Path) -> None:
    if shutil.which("kaggle") is None:
        raise DataError("the `kaggle` command-line tool is not installed; see https://github.com/Kaggle/kaggle-api")
    directory.mkdir(parents=True, exist_ok=True)
    command = ["kaggle", "datasets", "download", "-d", "retailrocket/ecommerce-dataset", "-f", "events.csv", "-p", str(directory)]
    subprocess.run(command, check=True)
    if (directory / "events.csv.zip").is_file():
        extract_member(directory / "events.csv.zip", "events.csv", directory)


def main() -> int:
    jobs = {"retailrocket/events.csv": fetch_retailrocket, "uci/online_shoppers_intention.csv": fetch_uci}
    try:
        for name, fetch in jobs.items():
            if not (RAW / name).is_file():
                fetch((RAW / name).parent)
            verify_file(RAW, name)
            print(f"ok {name} {EXPECTED_SHA256[name]}")
    except (DataError, OSError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
