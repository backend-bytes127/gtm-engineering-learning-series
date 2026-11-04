"""Entry point: python3 -m pipeline.run  (from projects/02-contact-list-merge)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from .build import COLUMNS, build_all
from .cluster import build_clusters, prepare
from .loaders import load_all

LOG = logging.getLogger("session3")
ROOT = Path(__file__).resolve().parent.parent
# Inputs and outputs can be redirected, e.g. GTM_DATA_DIR=/path/to/exports GTM_OUTPUT_DIR=/tmp/out
DATA = Path(os.environ.get("GTM_DATA_DIR", ROOT / "sample-data"))
OUT = Path(os.environ.get("GTM_OUTPUT_DIR", ROOT / "output"))

COLUMN_MAP = (
    ("Company Name", "Company name", "Organisation / Company", "Company Name", "companyName", "Company", "Company Name"),
    ("Website", "-", "-", "-", "(LinkedIn company URL is not a website)", "Website", "Website"),
    ("HQ Location", "City (contact's, not HQ)", "City (contact's)", "City / Country (contact's)", "companyLocation", "Company City + Company Country", "Company City + Company Country"),
    ("Company Size", "How many employees...?", "Emp Strength", "Company Size", "-", "# Employees", "Employees"),
    ("Contact Person Name", "Full name", "Name of Delegate / Full Name", "First Name + Last Name", "fullName", "First Name + Last Name", "First Name + Last Name"),
    ("First Name", "(split Full name)", "(split)", "First Name", "firstName", "First Name", "First Name"),
    ("Last Name", "(split Full name)", "(split)", "Last Name", "lastName", "Last Name", "Last Name"),
    ("Designation/Job Title", "Job title", "Designation / Job Title", "Job Title", "title", "Title", "Job Title"),
    ("LinkedIn URL", "-", "-", "LinkedIn Profile", "defaultProfileUrl (linkedInProfileUrl/profileUrl are Sales Nav / ACwAA)", "Person Linkedin Url", "LinkedIn Contact Profile URL"),
    ("Mobile No.", "Phone number", "Contact No / Phone / Notes 'Mob ...'", "Phone Number", "-", "Mobile Phone (+ Work Direct only if corroborated); NOT Corporate Phone", "Mobile phone; NOT Direct Phone Number"),
    ("Email ID", "Work email", "Email ID / Email", "Email Address", "-", "Email", "Email Address"),
)
MAP_HEAD = ("Final field", "01 Google Ads", "02 Event", "03 LinkedIn Form", "04 Scraped LinkedIn", "05 Apollo", "06 ZoomInfo")


def _sheet(wb: openpyxl.Workbook, title: str, head: tuple, rows: list[tuple]) -> None:
    ws = wb.create_sheet(title)
    ws.append(head)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append(list(r))
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = min(60, max(12, max(len(str(c.value or "")) for c in col) + 2))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    recs, removed = load_all(DATA)
    preps = prepare(recs)
    clusters, links = build_clusters(preps)
    people, dropped = build_all(clusters, preps)
    for cluster in dropped:
        removed.append(type(removed[0])(cluster[0].rec.source, cluster[0].rec.ref, cluster[0].rec.full, "",
                                        "no company in any source"))

    wb = openpyxl.load_workbook(DATA / "00_Final_Output_Template_and_Rules.xlsx")
    ws = wb["Final Output"]
    for p in people:
        ws.append([p.row[c] for c in COLUMNS])
    for col, width in zip("ABCDEFGHIJK", (28, 28, 26, 14, 24, 14, 16, 34, 52, 16, 42), strict=False):
        ws.column_dimensions[col].width = width
    wb.save(OUT / "Final_Contact_List.xlsx")

    audit = openpyxl.Workbook()
    audit.remove(audit.worksheets[0])
    _sheet(audit, "Column Mapping", MAP_HEAD, list(COLUMN_MAP))
    _sheet(audit, "Removed Records", ("Source", "Row", "Name", "Company", "Reason"),
           [(r.source, r.ref, r.name, r.company, r.reason) for r in removed])
    _sheet(audit, "Merge Log", ("Contact", "Company", "Records merged", "Source records"),
           [(p.row["Contact Person Name"], p.row["Company Name"], len(p.refs), "; ".join(p.refs)) for p in people])
    _sheet(audit, "Link Decisions", ("Link type", "Record A", "Record B", "Detail"),
           [(link.kind, link.a, link.b, link.note) for link in links])
    _sheet(audit, "Review Flags", ("Contact", "Company", "Flag"),
           [(p.row["Contact Person Name"], p.row["Company Name"], f) for p in people for f in p.flags])
    audit.save(OUT / "Cleaning_Audit.xlsx")
    LOG.info("%d source rows -> %d removed -> %d people", len(recs) + len(removed), len(removed), len(people))
    print(f"{len(recs) + len(removed)} source rows | {len(removed)} removed | {len(people)} final contacts")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
