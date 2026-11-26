"""Download the public datasets into data/raw/ (git-ignored) and check their SHA-256.

    python fetch_data.py                # main dataset only (UCI, no account needed)
    python fetch_data.py --candidates   # also the comparison set (needs a configured `kaggle` command)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

RAW = Path(__file__).resolve().parent / "data" / "raw"
UCI_URL = "https://archive.ics.uci.edu/static/public/222/bank+marketing.zip"
UCI_INNER_ZIP = "bank-additional.zip"
UCI_MEMBER = "bank-additional/bank-additional-full.csv"
UCI_TARGET = "uci/bank-additional-full.csv"
CHECKSUMS = {
    UCI_TARGET: "74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8",
    "maven/accounts.csv": "e5242324768a563fc632cddfed49a29acbbf2892b8a3c6453cc9650de9ae0358",
    "maven/data_dictionary.csv": "22b34e498d07e3d7f322afdbf81d70a5dc0a389792944e50ca2af86a3597f0af",
    "maven/products.csv": "7c1c8cbbdb6d4c286902e1985eeb529a36366d6a43f43cd4a93c4b1da2a6eb84",
    "maven/sales_pipeline.csv": "825ce8f6c32d4009548b468df3173d55a46fd73f2531f532c5459371dc52adf2",
    "maven/sales_teams.csv": "aeff1272ebe196f5a27e3fc0578aa27abf48ed9ae461aa344fb95990e5ad8bd1",
}
KAGGLE_SETS = {"maven": "innocentmfa/crm-sales-opportunities"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(relative: str, root: Path | None = None) -> None:
    actual = sha256((root or RAW) / relative)
    if actual != CHECKSUMS[relative]:
        raise ValueError(f"checksum mismatch for {relative}: got {actual}. The source changed; do not trust old results.")
    print(f"ok  {relative}")


def extract_uci(archive: bytes, root: Path | None = None) -> Path:
    """Read exactly one named member from the nested zip; nothing else is written to disk."""
    with zipfile.ZipFile(io.BytesIO(archive)) as outer:
        inner_bytes = outer.read(UCI_INNER_ZIP)
    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner:
        content = inner.read(UCI_MEMBER)
    target = (root or RAW) / UCI_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def fetch_uci() -> None:
    if not (RAW / UCI_TARGET).exists():
        with urllib.request.urlopen(UCI_URL, timeout=120) as response:  # noqa: S310 (fixed https URL)
            extract_uci(response.read())
    verify(UCI_TARGET)


def fetch_kaggle() -> None:
    for folder, slug in KAGGLE_SETS.items():
        expected = [name for name in CHECKSUMS if name.startswith(folder + "/")]
        if not all((RAW / name).exists() for name in expected):
            (RAW / folder).mkdir(parents=True, exist_ok=True)
            subprocess.run(["kaggle", "datasets", "download", slug, "-p", str(RAW / folder), "--unzip"], check=True)
        for name in expected:
            verify(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidates", action="store_true")
    args = parser.parse_args(argv)
    try:
        fetch_uci()
        if args.candidates:
            fetch_kaggle()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
