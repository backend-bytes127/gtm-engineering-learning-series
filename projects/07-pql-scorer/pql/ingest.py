"""Read the downloaded files and check they are the files DATA.md describes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

EXPECTED_SHA256 = {
    "retailrocket/events.csv": "3745aa83238b1e6d44d8fda209807899f420084398f94ddf745f3cbcfecbf9e7",
    "uci/online_shoppers_intention.csv": "b3055ee355f59134d851d32641183cb4a8b45def7124d2f50442a042f358e0d9",
}


class DataError(RuntimeError):
    """A data file is missing or is not the expected one."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(raw_dir: Path, name: str, expected: dict[str, str] | None = None) -> Path:
    path = raw_dir / name
    if not path.is_file():
        raise DataError(f"missing {name}; run `python fetch_data.py` first")
    wanted = (expected or EXPECTED_SHA256)[name]
    actual = sha256_of(path)
    if actual != wanted:
        raise DataError(f"checksum mismatch for {name}: expected {wanted}, got {actual}")
    return path


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)
