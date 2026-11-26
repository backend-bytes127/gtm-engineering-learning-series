"""Download the Criteo attribution file into data/raw/ and verify its SHA-256.

The dataset is CC BY-NC-SA 4.0: non-commercial use only. Nothing in data/raw/ may be committed.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

URL = "https://huggingface.co/datasets/criteo/criteo-attribution-dataset/resolve/main/criteo_attribution_dataset.tsv.gz"
SHA256 = "94ac7a465564349bc7ba008602211d5990a3c53cc133abc0aadef61ea2391a98"
SIZE_BYTES = 653_015_824
TARGET = Path(__file__).resolve().parent / "data" / "raw" / "criteo_attribution_dataset.tsv.gz"
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, target: Path, expected: str, max_bytes: int = SIZE_BYTES) -> Path:
    """Write to a .part file, check size and hash, and only then give it the real name."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and sha256_of(target) == expected:
        return target
    partial = target.with_suffix(target.suffix + ".part")
    received = 0
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as handle:
        while block := response.read(CHUNK):
            received += len(block)
            if received > max_bytes:
                break
            handle.write(block)
    actual = sha256_of(partial)
    if received > max_bytes or actual != expected:
        partial.unlink()
        raise ValueError(f"download rejected: {received} bytes, sha256 {actual}, expected {expected}")
    partial.replace(target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-noncommercial-licence", action="store_true", help="confirm your use is non-commercial")
    args = parser.parse_args(argv)
    if not args.accept_noncommercial_licence:
        print("The Criteo dataset is CC BY-NC-SA 4.0 (non-commercial). Re-run with --accept-noncommercial-licence.", file=sys.stderr)
        return 2
    try:
        path = download(URL, TARGET, SHA256)
    except (OSError, ValueError) as error:
        print(f"Download failed: {error}", file=sys.stderr)
        return 1
    print(f"OK: data/raw/{path.name} matches sha256 {SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
