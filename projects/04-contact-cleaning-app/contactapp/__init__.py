"""Project 04: a web app around Project 02's cleaning and merge code."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_02 = Path(__file__).resolve().parents[2] / "02-contact-list-merge"
if str(PROJECT_02) not in sys.path:  # the `pipeline` package lives in project 02; it is reused, not copied
    sys.path.insert(0, str(PROJECT_02))
