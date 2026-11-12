#!/usr/bin/env python3
"""Regenerate sample-data/contacts.csv: a synthetic contact list with deliberate defects.

Every name, company and domain is fictional (domains end in .example). The defects are listed in sample-data/README.md
so each validation rule has something to catch.
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample-data" / "contacts.csv"
HEADER = ["Full Name", "Company", "Job Title", "Work Email", "LinkedIn Profile", "Sequence", "Status"]

COMPANIES = {
    "Harbor Demo": "harbor-demo.example",
    "Kestrel Demo": "kestrel-demo.example",
    "Lumen Demo": "lumen-demo.example",
    "Orchard Demo": "orchard-demo.example",
    "Pinnacle Demo": "pinnacle-demo.example",
    "Quarry Demo": "quarry-demo.example",
    "Ridge Demo": "ridge-demo.example",
    "Summit Demo": "summit-demo.example",
}
PEOPLE = [  # (name, company, title)
    ("Mira Castellan", "Harbor Demo", "Head of Sales"),
    ("Jonas Wekesa", "Harbor Demo", "Revenue Operations Manager"),
    ("Priya Ankersen", "Kestrel Demo", "VP Sales"),
    ("Tomas Bellweather", "Kestrel Demo", "Sales Director"),
    ("Imogen Strand", "Kestrel Demo", "Demand Generation Lead"),
    ("Rafael Odenkirk", "Lumen Demo", "Chief Revenue Officer"),
    ("Sunita Marlowe", "Lumen Demo", "Head of Growth"),
    ("Evander Pike", "Lumen Demo", "Sales Operations Lead"),
    ("Odessa Quill", "Orchard Demo", "Director of Business Development"),
    ("Callum Reyes", "Orchard Demo", "Account Executive Lead"),
    ("Naledi Fairbrook", "Orchard Demo", "Head of Marketing"),
    ("Bastian Holloway", "Pinnacle Demo", "Sales Manager"),
    ("Yara Thornquist", "Pinnacle Demo", "Chief Commercial Officer"),
    ("Dmitri Aldous", "Pinnacle Demo", "Growth Marketing Manager"),
    ("Freya Lindqvist", "Quarry Demo", "VP Revenue"),
    ("Kofi Marchetti", "Quarry Demo", "Head of Partnerships"),
    ("Lucia Vandermeer", "Quarry Demo", "Sales Enablement Manager"),
    ("Soren Okafor", "Ridge Demo", "Director of Sales"),
    ("Anika Whitlock", "Ridge Demo", "Revenue Operations Lead"),
    ("Hugo Ferreira-Bloom", "Ridge Demo", "Head of Demand Gen"),
    ("Zainab Kowalczyk", "Summit Demo", "Chief Executive Officer"),
    ("Leopold Nyström", "Summit Demo", "VP Marketing"),
    ("Mei-Ling Abernathy", "Summit Demo", "Senior Sales Manager"),
]


def slug(name: str) -> str:
    return "".join(ch for ch in name.lower().replace(" ", ".").replace("-", "") if ch.isalnum() or ch == ".").replace("ö", "o")


def li(name: str, n: int) -> str:
    return f"https://www.linkedin.com/in/{slug(name).replace('.', '-')}-{n:04x}"


def build() -> list[list[str]]:
    rows: list[list[str]] = []
    for i, (name, company, title) in enumerate(PEOPLE, start=1):
        rows.append(
            [
                name,
                company,
                title,
                f"{slug(name)}@{COMPANIES[company]}",
                li(name, 0x1A00 + i),
                "Outbound Intro" if i % 4 else "",
                "",
            ]
        )
    # Reachable on one channel only: valid on the other channel, so these are kept.
    rows[3][3] = ""  # LinkedIn only
    rows[9][4] = ""  # email only
    rows[14][3] = ""
    rows[18][4] = ""
    # A missing company and title: filled from fallbacks in the templates, not removed.
    rows[5][1], rows[7][2] = "", ""
    # Defects ------------------------------------------------------------------------------------------------------
    rows.append(
        ["Gideon Marsh", "Harbor Demo", "Sales Lead", "gideon.marsh@harbor-demo", "", "Outbound Intro", ""]
    )  # bad e-mail, no LinkedIn
    rows.append(
        ["Hester Vale", "Lumen Demo", "Sales Lead", "hester.vale@gmial.com", li("Hester Vale", 0x2001), "Outbound Intro", ""]
    )  # typo, LinkedIn kept
    rows.append(
        ["Ivo Pruitt", "Ridge Demo", "Sales Lead", "ivo@mailinator.com", "", "Outbound Intro", ""]
    )  # disposable, no LinkedIn
    rows.append(
        [
            "Jada Finch",
            "Summit Demo",
            "Office Manager",
            "info@summit-demo.example",
            li("Jada Finch", 0x2003),
            "Outbound Intro",
            "",
        ]
    )  # role account
    rows.append(
        ["Mira Castellan", "Harbor Demo", "Head of Sales", rows[0][3].upper(), "", "Outbound Intro", ""]
    )  # duplicate by e-mail
    rows.append(
        [
            "Priya A.",
            "Kestrel Demo",
            "VP Sales",
            "priya.other@kestrel-demo.example",
            rows[2][4].replace("https://www.", "http://"),
            "",
            "",
        ]
    )  # dup by LinkedIn
    rows.append(
        [
            "Kai Dunmore",
            "Orchard Demo",
            "Sales Lead",
            "kai.dunmore@orchard-demo.example",
            li("Kai Dunmore", 0x2006),
            "Outbound Intro",
            "Unsubscribed",
        ]
    )  # status
    rows.append(
        ["Lena Ostrow", "Quarry Demo", "Sales Lead", "do.not.contact@harbor-demo.example", "", "Outbound Intro", ""]
    )  # suppression: e-mail
    rows.append(
        ["Marek Quist", "Pinnacle Demo", "Sales Lead", "marek.quist@blocked-demo.example", "", "Outbound Intro", ""]
    )  # suppression: domain
    rows.append(
        ["Nadia Brandt", "Ridge Demo", "Sales Lead", "", "https://www.linkedin.com/in/previous-optout-8821", "Outbound Intro", ""]
    )  # suppression: LinkedIn
    rows.append(
        [
            "Orla Finnegan",
            "Lumen Demo",
            "Sales Lead",
            "orla@lumen-demo.example",
            "https://www.linkedin.com/company/lumen-demo",
            "Outbound Intro",
            "",
        ]
    )  # company page, e-mail kept
    rows.append(["Pavel Strom", "Kestrel Demo", "Sales Lead", "", "", "Outbound Intro", ""])  # no channel
    rows.append(["", "Quarry Demo", "Sales Lead", "someone@quarry-demo.example", "", "Outbound Intro", ""])  # no name
    return rows


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = build()
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT.relative_to(OUT.parents[2])}")


if __name__ == "__main__":
    main()
