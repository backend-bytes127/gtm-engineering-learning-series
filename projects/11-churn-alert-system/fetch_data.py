"""Download UCI Online Retail II (CC BY 4.0) into data/raw/ and verify SHA-256. Run: python fetch_data.py"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
RAW = Path(__file__).resolve().parent / "data" / "raw"
ZIP_NAME = "online_retail_ii.zip"
XLSX_NAME = "online_retail_II.xlsx"
SHA256 = {
    ZIP_NAME: "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb",
    XLSX_NAME: "bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}")


def main(raw: Path = RAW, url: str = URL) -> int:
    raw.mkdir(parents=True, exist_ok=True)
    archive = raw / ZIP_NAME
    if not archive.exists():
        part = archive.with_suffix(".part")
        urllib.request.urlretrieve(url, part)
        part.replace(archive)
    verify(archive, SHA256[ZIP_NAME])
    target = raw / XLSX_NAME
    if not target.exists():
        with zipfile.ZipFile(archive) as bundle:
            target.write_bytes(bundle.read(XLSX_NAME))  # one named member only: no path from the archive is trusted
    verify(target, SHA256[XLSX_NAME])
    print(f"verified {ZIP_NAME} and {XLSX_NAME} in {raw.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
