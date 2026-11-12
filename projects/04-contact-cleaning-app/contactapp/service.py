"""Run the clean -> standardize -> consolidate pipeline on uploaded files and keep the result as plain data."""
from __future__ import annotations

import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pipeline import run as pipeline_run  # noqa: I001  (project 02 is put on sys.path by the package)
from pipeline.build import COLUMNS  # noqa: I001

from . import PROJECT_02, intake

SAMPLE_DIR = PROJECT_02 / "sample-data"


@dataclass(frozen=True)
class RunResult:
    summary: dict
    rows: tuple[dict, ...]
    removed: tuple[dict, ...]
    final_xlsx: bytes
    audit_xlsx: bytes


def _summarise(result: pipeline_run.Consolidated) -> dict:
    merged = sum(1 for p in result.people if len(p.refs) > 1)
    reasons = Counter(r.reason for r in result.removed)
    return {
        "source_rows": result.source_rows,
        "removed": len(result.removed),
        "removed_reasons": dict(reasons.most_common()),
        "kept": result.source_rows - len(result.removed),
        "people": len(result.people),
        "merged_people": merged,
        "duplicates_merged": sum(len(p.refs) - 1 for p in result.people),
        "review_flags": sum(len(p.flags) for p in result.people),
        "with_email": sum(1 for p in result.people if p.row["Email ID"]),
        "with_mobile": sum(1 for p in result.people if p.row["Mobile No."]),
        "with_linkedin": sum(1 for p in result.people if p.row["LinkedIn URL"]),
    }


def _rows(result: pipeline_run.Consolidated) -> tuple[dict, ...]:
    return tuple({**{c: p.row[c] or "" for c in COLUMNS}, "_sources": len(p.refs), "_flags": list(p.flags)} for p in result.people)


def _run_folder(folder: Path) -> RunResult:
    result = pipeline_run.consolidate(folder)
    with tempfile.TemporaryDirectory() as out:
        final, audit = Path(out) / "final.xlsx", Path(out) / "audit.xlsx"
        pipeline_run.write_final(result.people, folder / intake.TEMPLATE_NAME, final)
        pipeline_run.write_audit(result, audit)
        final_bytes, audit_bytes = final.read_bytes(), audit.read_bytes()
    removed = tuple({"source": r.source, "ref": r.ref, "name": r.name, "company": r.company, "reason": r.reason} for r in result.removed)
    return RunResult(_summarise(result), _rows(result), removed, final_bytes, audit_bytes)


def run_files(files: Mapping[str, bytes], template: bytes | None = None) -> RunResult:
    """Validate and process an upload. Raises intake.IntakeError for unusable files."""
    with tempfile.TemporaryDirectory() as work:
        return _run_folder(intake.stage(files, template, Path(work)))


def run_sample() -> RunResult:
    """Process the bundled synthetic sample, for trying the app without any files."""
    return _run_folder(SAMPLE_DIR)
