#!/usr/bin/env python3
"""Fail if the working tree contains secrets, private identifiers or files that must never be committed.

Run by `make secrets`, the pre-commit hook (.githooks/pre-commit) and CI. Exit code 1 on any finding.
Scans text files only; binary/Office files are checked by name. Fictional sample data lives in sample-data/.
Also fails if the committer's own name, e-mail or OS user name (read from git/OS at run time) appears in any file.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

FORBIDDEN_NAMES = (
    re.compile(r"(^|/)client_secret.*\.json$"), re.compile(r"(^|/)\.env($|\.(?!example$))"),
    re.compile(r"\.(pem|key|p12|pfx)$"), re.compile(r"(^|/)~\$"), re.compile(r"(^|/)\.DS_Store$"),
    re.compile(r"(^|/)\.claude/"), re.compile(r"(^|/)secrets?\.(local\.)?(md|json|txt|ya?ml)$"),
    re.compile(r"\.(zip|sqlite|db)$"),
)
SECRET_PATTERNS = {
    "Google OAuth client secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),
    "Google OAuth client id": re.compile(r"\b\d{9,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "Google access token": re.compile(r"ya29\.[0-9A-Za-z_-]{20,}"),
    "Apify token": re.compile(r"apify_api_[A-Za-z0-9]{20,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Bearer token literal": re.compile(r"Bearer\s+(?!<|\{|YOUR|\$)[A-Za-z0-9._-]{24,}"),
    "Google spreadsheet/drive id": re.compile(r"(?<![A-Za-z0-9_-])1[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"),
    "Absolute home path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "output", ".venv", "venv"}
SKIP_PARTS = ("sample-data", "expected-output")  # fictional data; Office files are not text-scanned anyway
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".json", ".md", ".yml", ".yaml", ".toml", ".txt", ".html", ".csv", ".sh",
                 ".cfg", ".ini", ".example", ".ipynb", ""}


def identity_tokens() -> list[str]:
    """The committer's own identity, read at run time so nothing personal is hard-coded in the repo.

    Covers global git name/e-mail, the OS user name and the home-directory name. (CI runners have none of these,
    so this check is a local guard; the pattern checks above are what CI enforces.)
    """
    if os.environ.get("CI"):  # CI runners have a generic user ("runner"); there is no personal identity to leak
        return []  # (.private-terms is git-ignored, so it does not exist on CI either)
    tokens = [os.environ.get("USER", ""), Path.home().name]
    for key in ("user.email", "user.name"):
        done = subprocess.run(["git", "config", "--global", key], capture_output=True, text=True)
        tokens.append(done.stdout.strip())
    private = ROOT / ".private-terms"  # optional, git-ignored: one word or phrase per line (names, street, employers)
    if private.is_file():
        tokens += [ln.strip() for ln in private.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return sorted({t for t in tokens if len(t) >= 4}, key=str.lower)


def tracked_candidates() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.splitlines()
    return [ROOT / p for p in out if p and (ROOT / p).is_file()]


def main() -> int:
    findings: list[str] = []
    identity = [(tok, re.compile(rf"(?<![A-Za-z0-9]){re.escape(tok)}(?![A-Za-z0-9])", re.IGNORECASE))
                for tok in identity_tokens()]  # whole-word match: a short user name must not hit inside longer words
    for path in tracked_candidates():
        rel = path.relative_to(ROOT).as_posix()
        if path == SELF or any(part in SKIP_DIRS for part in path.parts):
            continue
        for rx in FORBIDDEN_NAMES:
            if rx.search(rel):
                findings.append(f"{rel}: forbidden file")
        if any(part in rel for part in SKIP_PARTS) or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        # embedded base64 images (notebook outputs, HTML data URIs) are random text, never secrets
        text = re.sub(r'"image/png": "[^"]*"', '"image/png": ""', text)
        text = re.sub(r"data:image/[a-z+]+;base64,[A-Za-z0-9+/=]+", "data:image;base64,", text)
        for _tok, rx in identity:
            for m in rx.finditer(text):
                findings.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: personal identity (git/OS user) in text")
        for label, rx in SECRET_PATTERNS.items():
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                findings.append(f"{rel}:{line}: {label}")
    for f in sorted(set(findings)):
        print(f"[secrets] {f}")
    print(f"[secrets] {'FAILED: ' + str(len(set(findings))) + ' finding(s)' if findings else 'clean'}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
