"""Where the web app keeps its data: one SQLite file and an uploads folder."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..rules import SendingRules
from ..store import Store

UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "app.sqlite"

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    def store(self) -> Store:
        self.root.mkdir(parents=True, exist_ok=True)
        return Store(self.db_path)

    def upload_path(self, upload_id: str) -> Path | None:
        if not UPLOAD_ID.match(upload_id):
            return None
        found = list(self.uploads.glob(f"{upload_id}.*"))
        return found[0] if found else None

    def wipe(self) -> None:
        self.db_path.unlink(missing_ok=True)
        shutil.rmtree(self.uploads, ignore_errors=True)


def first_window_start(rules: SendingRules, now: datetime | None = None) -> datetime:
    """When a launch may start: right now if the sending window is open, else the next opening, in UTC."""
    tz = ZoneInfo(rules.timezone)
    moment = now or datetime.now(timezone.utc)
    local = moment.astimezone(tz)
    if local.isoweekday() in rules.active_days and rules.start_hour <= local.hour < rules.end_hour:
        return moment
    day = local.date()
    for _ in range(14):
        candidate = datetime.combine(day, time(rules.start_hour), tzinfo=tz)
        if candidate >= local and candidate.isoweekday() in rules.active_days:
            return candidate.astimezone(timezone.utc)
        day += timedelta(days=1)
    raise ValueError("no active day found in the next two weeks")
