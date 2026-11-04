"""The walkthrough notebook and the sample-data README must never show a name, e-mail, slug or phone from the sample.

It masks them at display time. This test scans everything a reader can see (markdown, code and every output, with
embedded chart images removed) so a later edit cannot quietly reintroduce one.
"""
import json
import re
from pathlib import Path

import pytest

from pipeline import normalize as N
from pipeline.loaders import load_all
from pipeline.run import DATA, ROOT

NOTEBOOK = Path(ROOT) / "notebooks" / "walkthrough.ipynb"
README = Path(ROOT) / "sample-data" / "README.md"
STOP = {"google", "test", "lead", "linkedin", "member", "asdf", "student", "freelancer"}


def visible_text() -> str:
    parts = []
    for cell in json.loads(NOTEBOOK.read_text())["cells"]:
        parts.append("".join(cell["source"]))
        for out in cell.get("outputs", []):
            data = out.get("data", {})
            parts.append("".join(out.get("text", [])))
            parts += ["".join(v) for k, v in data.items() if k in ("text/plain", "text/html")]
    return "\n".join(parts)


@pytest.fixture(scope="module")
def secrets():
    kept, removed = load_all(DATA)
    names = {w for r in kept for w in r.full.split() if len(w) >= 3}
    names |= {w for r in removed for w in r.name.split() if len(w) >= 3 and w.lower() not in STOP}
    emails = {e for r in kept for raw in r.emails for e in N.split_emails(raw)}
    slugs = {r.slug for r in kept if r.slug}
    phones = {re.sub(r"\D", "", raw) for r in kept for raw, _ in r.phones}
    return names, emails, slugs, {p for p in phones if len(p) >= 10 and len(set(p)) > 1}


@pytest.mark.skipif(not NOTEBOOK.exists(), reason="notebook not built")
def test_no_person_name_is_visible(secrets):
    names, *_ = secrets
    text = visible_text()
    leaked = sorted(n for n in names if re.search(rf"\b{re.escape(n)}\b", text, re.I))
    assert not leaked, f"unmasked names in the notebook: {leaked}"


@pytest.mark.skipif(not NOTEBOOK.exists(), reason="notebook not built")
def test_no_email_slug_or_phone_is_visible(secrets):
    _, emails, slugs, phones = secrets
    text = visible_text()
    assert not [e for e in emails if e.split("@")[0] in text and e in text], "unmasked e-mail address"
    assert not [s for s in slugs if s in text], "unmasked LinkedIn slug"
    digits_only = re.sub(r"[^\d]", "", text.replace(",", " "))
    assert not [p for p in phones if p in digits_only], "unmasked phone number"
    # the generic examples used in the explanations must not be sample data either
    assert "Jane Doe" in text


@pytest.mark.skipif(not NOTEBOOK.exists(), reason="notebook not built")
def test_the_masking_is_actually_visible():
    """Guard against masking being switched off silently: masked shapes must appear."""
    text = visible_text()
    assert re.search(r"[A-Z]\*{2,}", text), "no masked names found"
    assert re.search(r"[a-z]\*{2,}@", text), "no masked e-mails found"


def test_sample_readme_shows_no_real_name_email_slug_or_phone(secrets):
    names, emails, slugs, phones = secrets
    text = README.read_text()
    assert not sorted(n for n in names if re.search(rf"\b{re.escape(n)}\b", text, re.I)), "unmasked name in sample README"
    assert not [e for e in emails if e in text], "unmasked e-mail in sample README"
    assert not [s for s in slugs if s in text], "unmasked slug in sample README"
    digits = re.sub(r"\D", "", text)
    assert not [p for p in phones if p in digits], "unmasked phone in sample README"
