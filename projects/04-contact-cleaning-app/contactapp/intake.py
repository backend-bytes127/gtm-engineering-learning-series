"""Accept the uploaded source files, check them, and stage them under the names the pipeline expects."""
from __future__ import annotations

import io
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from . import PROJECT_02

MAX_FILE_BYTES = 10 * 1024 * 1024
TEMPLATE_NAME = "00_Final_Output_Template_and_Rules.xlsx"
BUNDLED_TEMPLATE = PROJECT_02 / "sample-data" / TEMPLATE_NAME


@dataclass(frozen=True)
class Slot:
    key: str
    label: str
    filename: str
    sheets: tuple[str, ...]


SLOTS: tuple[Slot, ...] = (
    Slot("01", "Google Ads lead form", "01_GoogleAds_LeadForm_Export.xlsx", ("leads",)),
    Slot("02", "Event delegates and scans", "02_Event_Delegates_and_Scans.xlsx", ("Delegate List", "Booth Scans")),
    Slot("03", "LinkedIn Lead Gen form", "03_LinkedIn_LeadGenForm_Export.xlsx", ("leads",)),
    Slot("04", "Scraped LinkedIn (Sales Navigator)", "04_LinkedIn_Scraped_SalesNav.xlsx", ("result",)),
    Slot("05", "Apollo export", "05_ThirdParty_Apollo_Export.xlsx", ("apollo-contacts-export",)),
    Slot("06", "ZoomInfo export", "06_ThirdParty_ZoomInfo_Export.xlsx", ("ZoomInfo Contacts",)),
)
SLOT_BY_KEY = {s.key: s for s in SLOTS}


class IntakeError(Exception):
    """One or more uploads cannot be used. `problems` maps a slot key to a plain-language reason."""

    def __init__(self, problems: Mapping[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in problems.items()))
        self.problems = dict(problems)


def _problem(data: bytes | None, sheets: tuple[str, ...]) -> str | None:
    if not data:
        return "no file was uploaded"
    if len(data) > MAX_FILE_BYTES:
        return f"the file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB"
    if not data.startswith(b"PK"):
        return "this is not an .xlsx workbook"
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    except Exception:  # openpyxl raises many types for corrupt files
        return "the workbook could not be opened"
    missing = [s for s in sheets if s not in wb.sheetnames]
    wb.close()
    return f"missing sheet {', '.join(repr(m) for m in missing)}" if missing else None


def check(files: Mapping[str, bytes], template: bytes | None) -> None:
    """Raise IntakeError listing every problem at once, so the user fixes them in one go."""
    problems = {s.key: p for s in SLOTS if (p := _problem(files.get(s.key), s.sheets))}
    if template is not None and (p := _problem(template, ("Final Output",))):
        problems["template"] = p
    if problems:
        raise IntakeError(problems)


def stage(files: Mapping[str, bytes], template: bytes | None, dest: Path) -> Path:
    """Write the checked files into `dest` with the canonical names and return `dest`."""
    check(files, template)
    for slot in SLOTS:
        (dest / slot.filename).write_bytes(files[slot.key])
    (dest / TEMPLATE_NAME).write_bytes(template if template is not None else BUNDLED_TEMPLATE.read_bytes())
    return dest
