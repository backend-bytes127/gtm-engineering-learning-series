"""Read only the named keys from an .env file, in memory. Values are never printed or logged."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def read_keys(path: Path, wanted: Iterable[str]) -> dict[str, str]:
    wanted_set = set(wanted)
    found: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        if key in wanted_set:
            found[key] = value.strip().strip("'\"")
    return found
