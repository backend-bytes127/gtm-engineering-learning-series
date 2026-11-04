#!/usr/bin/env python3
"""Generate the small SYNTHETIC sample workbooks used by the tests, parity check and end-to-end run.

Every person, company, e-mail and number is invented. The workbooks reproduce the *shape* and the *kinds of mess*
found in real lead exports (column names, date formats, phone columns of different trust, typos, test rows,
hidden profiles, name twins, a job changer), so each rule in the pipeline has something to bite on.

    python3 scripts/make_sample_data.py        # rewrites sample-data/*.xlsx
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent.parent / "sample-data"
FINAL_COLUMNS = ["Company Name", "Website", "HQ Location", "Company Size", "Contact Person Name", "First Name",
                 "Last Name", "Designation/Job Title", "LinkedIn URL", "Mobile No.", "Email ID"]
RULES = [  # paraphrased in our own words, one line per field / merge rule
    ("Field", "How to standardize it"),
    ("Company Name", "One name per company: no legal suffix, fixed casing and typos."),
    ("Website", "Root domain, lowercase; no scheme, www, path or tracking parameters."),
    ("HQ Location", "City, Country of the company HQ (not the contact's city)."),
    ("Company Size", "One of eight buckets from 1-10 to 10,001+."),
    ("Contact Person Name", "Formal first + last, proper case, as on the LinkedIn slug; no salutations, credentials, emoji."),
    ("Designation/Job Title", "Spelled out in full; headline text removed."),
    ("LinkedIn URL", "https://www.linkedin.com/in/<slug>; Sales Navigator and ACwAA ids do not count."),
    ("Mobile No.", "E.164, mobile only; no board or direct lines."),
    ("Email ID", "Lowercase, one address; work e-mail first, personal only if no work e-mail; blank if none."),
    ("Merge", "One row per person; latest dated source wins for employer/title; ZoomInfo > Apollo > rest for company facts."),
]


def sheet(wb: openpyxl.Workbook, title: str, header: list[str], rows: list[list], first: bool = False):
    ws = wb.create_sheet(title)
    ws.append(header)
    for r in rows:
        ws.append(r)
    return ws


def save(wb: openpyxl.Workbook, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if "Sheet" in wb.sheetnames:  # the default sheet openpyxl creates
        del wb["Sheet"]
    wb.save(OUT / name)


def template() -> None:
    wb = openpyxl.Workbook()
    sheet(wb, "Final Output", FINAL_COLUMNS, [], first=True)
    ws = wb.create_sheet("Rules")
    for r in RULES:
        ws.append(list(r))
    save(wb, "00_Final_Output_Template_and_Rules.xlsx")


def google_ads() -> None:
    h = ["Lead ID", "Time submitted", "Campaign name", "Is test", "Full name", "Work email", "Phone number",
         "Company name", "Job title", "How many employees does your company have?", "City"]
    t = "2026-10-{:02d} {} IST"
    rows = [
        ["g01", t.format(5, "13:09:15"), "IN_Search_GTM", "FALSE", "LENA PARK", "lena.park@kestrellogistics.com", "98000 10001", "Kestrel Logistics Pvt Ltd", "Mktg Manager", "340", "Greater Pune Area"],
        ["g02", t.format(6, "09:12:00"), "IN_Search_GTM", "FALSE", "omar diaz", "omardiaz7731x@gmail.com", "09700020001", "Kestrel", "Dir. Sales", "SMB", "Pune"],
        ["g03", t.format(7, "17:40:21"), "IN_Search_GTM", "FALSE", "Tom Baker", "tom.baker@lumenretail.con", "NA", "Lumen Retial", "Head of IT", "88", "London"],
        ["g04", t.format(8, "10:01:44"), "IN_Search_GTM", "FALSE", "Nina Cho", "nina.cho@sparrowfin.io; info@sparrowfin.io", "0000000000", "Sparrow Fintech Pte. Ltd.", "Sr Mgr - Sales", "201 to 500", "SINGAPORE"],
        ["g05", t.format(8, "10:01:44"), "IN_Search_GTM", "FALSE", "Nina Cho", "nina.cho@sparrowfin.io; info@sparrowfin.io", "0000000000", "Sparrow Fintech Pte. Ltd.", "Sr Mgr - Sales", "201 to 500", "SINGAPORE"],  # exact duplicate
        ["g06", t.format(9, "08:00:00"), "IN_Search_GTM", "TRUE", "Google Test", "lead-test@google-test.invalid", "0000000000", "Google Test Co", "QA", "51-200", "Mumbai"],
        ["g07", t.format(9, "08:05:00"), "IN_Search_GTM", "FALSE", "Alex Student", "alexstudent@gmail.com", "NA", "Student", "Looking for job", "1-10", "Pune"],
        ["g08", t.format(9, "08:09:00"), "IN_Search_GTM", "FALSE", "asdf asdf", "asdf@asdf.invalid", "1234567890", "asdf", "asdf", "1-10", "asdf"],
    ]
    save(_wb("leads", h, rows), "01_GoogleAds_LeadForm_Export.xlsx")


def _wb(title: str, header: list[str], rows: list[list]) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    sheet(wb, title, header, rows, first=True)
    return wb


def event() -> None:
    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Delegate List")
    ws.append(["Example Summit 2026"])                                   # banner rows above the header
    ws.append(["Pune | 18-19 September 2026 | Delegate List (Final)"])
    ws.append(["Confidential: for sponsor use only"])
    ws.append([])
    ws.append(["S.No", "Name of Delegate", "Organisation", "Designation", "Contact No", "Email ID", "City", "Emp Strength", "Pass Type", "Attended?"])
    d = [
        [1, "PARK, LENA", "Kestrel", "Chief Rev Officer", "9800010002", " lpark@kestrellogistics.com  ", "Pune", "201-500", "VIP", "Y"],
        [2, "Mr. Maya Iyer", "Driftwood Pay Pte. Ltd.", "Growth Head", "+6590001234", "maya.iyer@driftwoodpay.com", "Singapore", "51-200", "Speaker", "Yes"],
        [3, "ravi menon", None, "Manager - Procurement", "9.18772E+11", "ravi.menon@sparrowfin.io", "SG", None, "Delegate", "No"],  # no company, damaged phone
        [4, "Sam Ortiz", "Harbor", "Purchase Manager", "080-43057296", "mailto:sam.ortiz@harborsoft.com", "Dubai", "SMB", "Delegate", "Y"],  # landline
    ]
    for r in d:
        ws.append(r)
    ws.append([])
    ws.append([None, "Total Delegates: 4"])                              # footer
    sc = wb.create_sheet("Booth Scans")
    sc.append(["Scan Time", "Badge ID", "Full Name", "Company", "Job Title", "Email", "Phone", "Scanned By", "Lead Rating", "Notes"])
    sc.append(["18/09/2026 13:25", "BDG-1", "Omar Diaz, CSPO", "Kestrel Logistics", "Director - Sales", "mailto:omar.diaz@kestrellogistics.com", None, "Staff 1", "Hot", "Send deck. Mob 9700020001"])
    sc.append(["19/09/2026 03:19", "BDG-2", "Hana Weiss", "Harbor Software", "Manager - RevOps", " hana.weiss@harborsoft.com ", None, "Staff 2", "Warm", None])
    save(wb, "02_Event_Delegates_and_Scans.xlsx")


def linkedin_form() -> None:
    h = ["Lead ID", "Submitted At", "First Name", "Last Name", "Email Address", "Phone Number", "Company Name",
         "Job Title", "Company Size", "City", "Country", "LinkedIn Profile"]
    rows = [
        ["l1", "10/09/2026, 02:15 PM", "Lena", "Park", "lena.park@kestrellogistics.com", "+91-9800010001", "Kestrel Logistics", "Marketing Manager", "201-500", "Pune", "IN", "https://www.linkedin.com/in/lena-park-1a2b3c4d/en"],
        ["l2", "10/20/2026, 11:03 AM", "Maya", "Iyer", "maya.iyer@sparrowfin.io", "6590001234 (WhatsApp)", "Sparrow Fintech", "VP, Marketing", "201-500", "Singapore", "SG", "https://uk.linkedin.com/in/maya-iyer-5e6f7a8b/"],
        ["l3", "10/14/2026, 09:30 AM", "Dr. Katherine", "Doyle, MBA", "katherine.doyle@tidewaterhealth.com", None, "Tidewater Health Inc.", "CMO", "1001-5000", "Austin, Texas Metropolitan Area", "US", "http://in.linkedin.com/in/katherine-doyle-3c4d5e6f"],
        ["l4", "10/11/2026, 04:54 PM", "Zed", "Quill", "zedquill88@gmail.com", "(512) 555-0188", "Tidewater Health", "Director of Operations", "1001-5000", "Austin", "US", "www.linkedin.com/in/zed-quill-4f5a6b7c/?utm_source=share&utm_medium=member_android"],
    ]
    save(_wb("leads", h, rows), "03_LinkedIn_LeadGenForm_Export.xlsx")


def scraped() -> None:
    h = ["profileUrl", "fullName", "firstName", "lastName", "companyName", "title", "companyLocation", "location",
         "timestamp", "defaultProfileUrl", "linkedInProfileUrl"]
    sn = "https://www.linkedin.com/sales/lead/{},NAME_SEARCH,abcd"
    pub = "https://www.linkedin.com/in/{}"
    acw = "https://www.linkedin.com/in/{}"
    rows = [
        [sn.format("ACwAAlena77"), "Lena Park", "Lena", "Park", "Kestrel Logistics Private Limited", "Chief Rev Officer | Ex-Founder", "Pune", "Pune", "2026-10-21T16:43:11.556Z", pub.format("lena-park-77"), acw.format("ACwAAlena77")],
        [sn.format("ACwAAmaya"), "Maya Iyer 🚀", "Maya", "Iyer 🚀", "Sparrow Fintech", "Vice President of Marketing", "Singapore", "SG", "2026-10-28T08:00:00.000Z", pub.format("maya-iyer-5e6f7a8b"), acw.format("ACwAAmaya")],
        [sn.format("ACwAAkate"), "Kate Doyle (Open to Connect)", "Kate", "Doyle (Open to Connect)", "Tidewater Health", "Chief Mktg Officer | GTM | Pipeline", "Austin, Texas, United States", "Austin, TX", "2026-10-25T03:41:43.506Z", pub.format("katherine-doyle-3c4d5e6f"), acw.format("ACwAAkate")],
        [sn.format("ACwAAhana"), "Hana Weiss", "Hana", "Weiss", "Harbor Software", "Manager - RevOps", "Dubai", "Dubai", "2026-10-22T11:00:00.000Z", acw.format("ACwAAhana"), acw.format("ACwAAhana")],
        [sn.format("ACwAAhana"), "Hana Weiss", "Hana", "Weiss", "Harbor Software", "Revenue Operations Manager", "Dubai", "DXB", "2026-10-27T09:30:00.000Z", acw.format("ACwAAhana"), acw.format("ACwAAhana")],
        [sn.format("ACwAAhide1"), "LinkedIn Member", "LinkedIn", "Member", "Kestrel Logistics", "Chief Operating Officer", None, None, "2026-10-26T10:55:55.000Z", None, None],
        [sn.format("ACwAAhide2"), "LinkedIn Member", "LinkedIn", "Member", "Sparrow Fintech", "Chief Technology Officer", None, None, "2026-10-25T21:53:37.000Z", None, None],
    ]
    save(_wb("result", h, rows), "04_LinkedIn_Scraped_SalesNav.xlsx")


def apollo() -> None:
    h = ["First Name", "Last Name", "Title", "Company", "Email", "Email Status", "Primary Email Last Verified At",
         "Work Direct Phone", "Mobile Phone", "Corporate Phone", "# Employees", "Person Linkedin Url", "Website",
         "City", "Country", "Company City", "Company Country"]
    na = "email_not_unlocked@domain.com"
    rows = [
        ["Lena", "Park", "Chief Revenue Officer", "Kestrel Logistics", "lpark@kestrellogistics.com", "Verified", "2026-01-20T14:01:17+00:00", "'+91 98000 10002", None, "'+912000000002", 512, "http://www.linkedin.com/in/lena-park-77", "http://www.kestrellogistics.com", "Pune", "India", "Pune", "India"],
        ["Omar", "Diaz", "Director of Sales", "Kestrel Logistics", "omar.diaz@kestrellogistics.com", "Verified", "2026-02-02T10:00:00+00:00", "'+91 97000 20001", None, "'+912000000003", 512, None, "http://www.kestrellogistics.com", "Pune", "India", "Pune", "India"],
        ["Maya", "Iyer", "Head of Growth", "Driftwood Pay", "maya.iyer@driftwoodpay.com", "Verified", "2026-02-10T09:00:00+00:00", None, "'+6590001234", "'+6563001111", 150, "http://www.linkedin.com/in/maya-iyer-5e6f7a8b", "http://www.driftwoodpay.com", "Singapore", "Singapore", "Singapore", "Singapore"],
        ["Sam", "Ortiz", "Director of Marketing", "Lumen Retail", "sam.ortiz@lumenretail.com", "Verified", "2026-03-11T09:00:00+00:00", None, "'+447700900123", None, 88, "http://www.linkedin.com/in/sam-ortiz-11aa22bb", "http://www.lumenretail.com", "London", "United Kingdom", "London", "United Kingdom"],
        ["Sam", "Ortiz", "Procurement Manager", "Harbor Software", "sam.ortiz@harborsoft.com", "Extrapolated", "2026-03-12T09:00:00+00:00", None, "'+971501234567", None, 410, "http://www.linkedin.com/in/sam-ortiz-99cc88dd", "http://www.harborsoft.com", "Dubai", "United Arab Emirates", "Dubai", "United Arab Emirates"],
        ["Kate", "Doyle", "Chief Marketing Officer", "Tidewater Health", "katherine.doyle@tidewaterhealth.com", "Verified", "2026-02-25T23:56:17+00:00", None, "'+15125550142", None, 1850, "http://www.linkedin.com/in/katherine-doyle-3c4d5e6f", "http://www.tidewaterhealth.com", "Austin", "United States", "Austin", "United States"],
        ["Ravi", "Menon", "Procurement Manager", "Sparrow Fintech", "ravi.menon@sparrowfin.io", "Verified", "2026-04-01T09:00:00+00:00", "'+65 91234567", None, "'+6563002222", 270, "http://www.linkedin.com/in/ravi-menon-9a8b7c6d", "http://www.sparrowfin.io", "Singapore", "Singapore", "Singapore", "Singapore"],
        ["Hana", "Weiss", "Revenue Operations Manager", "Harbor Software", na, "Unavailable", None, None, None, None, 410, None, "http://www.harborsoft.com", "Dubai", "United Arab Emirates", "Dubai", "United Arab Emirates"],
    ]
    save(_wb("apollo-contacts-export", h, rows), "05_ThirdParty_Apollo_Export.xlsx")


def zoominfo() -> None:
    h = ["First Name", "Last Name", "Job Title", "Direct Phone Number", "Email Address", "Mobile phone", "Person City",
         "Country", "Company Name", "Website", "Employees", "LinkedIn Contact Profile URL", "Company City", "Company Country"]
    rows = [
        ["Lena", "Park", "Marketing Manager", "+912000000001", "lena.park@kestrellogistics.com", "+91 9800010001", "Pune", "India", "Kestrel Logistics", "www.kestrellogistics.com", 340, "linkedin.com/in/lena-park-1a2b3c4d", "Pune", "India"],
        ["Zed", "Quill", "Director of Operations", None, None, None, "Austin", "United States", "Tidewater Health", "www.tidewaterhealth.com", 1900, "linkedin.com/in/zed-quill-4f5a6b7c", "Austin", "United States"],
        ["Nina", "Cho", "Sr Mgr - Sales", "+6598765432", "nina.cho@sparrowfin.io", "+65 8123 4567", "Singapore", "Singapore", "Sparrow Fintech", "www.sparrowfin.io", 265, "linkedin.com/in/nina-cho-2d3e4f5a", "Singapore", "Singapore"],
        ["Ravi", "Menon", "Procurement Manager", "+6598765433", "ravi.menon@sparrowfin.io", None, "Singapore", "Singapore", "Sparrow Fintech", "www.sparrowfin.io", 265, "linkedin.com/in/ravi-menon-9a8b7c6d", "Singapore", "Singapore"],
    ]
    save(_wb("ZoomInfo Contacts", h, rows), "06_ThirdParty_ZoomInfo_Export.xlsx")


if __name__ == "__main__":
    for build in (template, google_ads, event, linkedin_form, scraped, apollo, zoominfo):
        build()
    print(f"wrote synthetic workbooks to {OUT}")
