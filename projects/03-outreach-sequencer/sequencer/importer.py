"""Step 1: read a contact list (CSV or XLSX) and map its columns to the tool's fields."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from .models import Contact

FIELDS = ("name", "first_name", "last_name", "company", "title", "email", "linkedin_url", "sequence", "status")

# Normalised header -> field. Normalising drops case and punctuation, so "E-mail", "e_mail" and "EMAIL" all match.
ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "full name", "contact name", "contact person name", "person", "lead name"),
    "first_name": ("first name", "firstname", "given name"),
    "last_name": ("last name", "lastname", "surname", "family name"),
    "company": ("company", "company name", "organisation", "organization", "account", "employer"),
    "title": ("title", "job title", "designation", "designation job title", "position", "role"),
    "email": ("email", "e mail", "email id", "email address", "work email"),
    "linkedin_url": ("linkedin url", "linkedin", "linkedin profile", "linkedin link", "profile url"),
    "sequence": ("sequence", "campaign", "cadence"),
    "status": ("status", "contact status", "lead status"),
}


class MappingError(ValueError):
    """The file cannot be turned into contacts with the given or guessed column mapping."""


@dataclass(frozen=True)
class ImportResult:
    contacts: tuple[Contact, ...]
    mapping: dict[str, str]  # field -> source header actually used
    unmapped: tuple[str, ...]  # source headers that no field used


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", header.lower()).strip()


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Guess field -> header from common header names. The first matching header wins for each field."""
    by_norm = {}
    for h in headers:
        by_norm.setdefault(_norm(h), h)
    mapping: dict[str, str] = {}
    for field_name, names in ALIASES.items():
        for alias in names:
            if alias in by_norm:
                mapping[field_name] = by_norm[alias]
                break
    return mapping


def _read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as fh:
            raw = list(csv.reader(fh))
    elif suffix in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        raw = [["" if v is None else str(v) for v in row] for row in wb.worksheets[0].iter_rows(values_only=True)]
        wb.close()
    else:
        raise MappingError(f"{path.name}: the contact list must be a CSV or XLSX file")
    if not raw:
        raise MappingError(f"{path.name}: the file is empty")
    return [h.strip() for h in raw[0]], raw[1:]


def _check_mapping(mapping: dict[str, str], headers: list[str]) -> None:
    for field_name, header in mapping.items():
        if field_name not in FIELDS:
            raise MappingError(f"unknown field '{field_name}' (fields: {', '.join(FIELDS)})")
        if header not in headers:
            raise MappingError(f"field '{field_name}' is mapped to column '{header}', which is not in the file")
    if "name" not in mapping and not ("first_name" in mapping or "last_name" in mapping):
        raise MappingError("no column for name (map 'name', or 'first_name' and 'last_name')")
    if "email" not in mapping and "linkedin_url" not in mapping:
        raise MappingError("no column for email or linkedin_url: there would be no way to reach anyone")


def _split_name(full: str) -> tuple[str, str]:
    parts = full.split()
    return (parts[0], " ".join(parts[1:])) if parts else ("", "")


def import_contacts(path: str | Path, mapping: dict[str, str] | None = None, default_sequence: str = "") -> ImportResult:
    """Read the file and return contacts. An explicit `mapping` overrides the guessed one field by field."""
    path = Path(path)
    headers, rows = _read_rows(path)
    used = {**suggest_mapping(headers), **(mapping or {})}
    _check_mapping(used, headers)
    index = {field_name: headers.index(header) for field_name, header in used.items()}

    def cell(row: list[str], field_name: str) -> str:
        i = index.get(field_name)
        return row[i].strip() if i is not None and i < len(row) else ""

    contacts: list[Contact] = []
    for number, row in enumerate(rows, start=1):
        if not any(c.strip() for c in row):
            continue
        first, last = cell(row, "first_name"), cell(row, "last_name")
        name = cell(row, "name") or " ".join(p for p in (first, last) if p)
        if name and not (first or last):
            first, last = _split_name(name)
        contacts.append(
            Contact(
                row=number,
                name=name,
                first_name=first,
                last_name=last,
                company=cell(row, "company"),
                title=cell(row, "title"),
                email=cell(row, "email"),
                linkedin_url=cell(row, "linkedin_url"),
                sequence=cell(row, "sequence") or default_sequence,
                source_status=cell(row, "status"),
            )
        )
    unmapped = tuple(h for h in headers if h and h not in used.values())
    return ImportResult(tuple(contacts), used, unmapped)


def read_preview(path: str | Path, limit: int = 5) -> tuple[list[str], list[list[str]], int]:
    """Headers, the first `limit` non-blank rows and the count of non-blank rows, for the column-mapping screen."""
    headers, rows = _read_rows(Path(path))
    filled = [r for r in rows if any(c.strip() for c in r)]
    return headers, [[c.strip() for c in r] for r in filled[:limit]], len(filled)
