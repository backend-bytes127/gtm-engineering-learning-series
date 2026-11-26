"""Read and summarise a project 11 style churn queue (``alert_queue_<date>.csv``)."""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

QUEUE_COLUMNS = (
    "rank",
    "customer_id",
    "churn_score",
    "net_180d_gbp",
    "value_at_risk_gbp",
    "primary_reason",
    "all_reasons",
    "suggested_action",
    "delivery_status",
)
_AMOUNT = re.compile(r"[0-9]{1,12}(\.[0-9]+)?")
_RANK = re.compile(r"[0-9]{1,6}")
_NAME = re.compile(r"alert_queue_([0-9]{4}-[0-9]{2}-[0-9]{2})\.csv")


class QueueError(ValueError):
    """The queue file does not match the contract. Nothing is posted."""


@dataclass(frozen=True)
class Account:
    rank: int
    customer_id: str
    value_at_risk_pence: int
    primary_reason: str
    suggested_action: str


def as_of_from_name(name: str) -> str:
    match = _NAME.fullmatch(name)
    if not match:
        raise QueueError("file name must be alert_queue_YYYY-MM-DD.csv")
    return match.group(1)


def to_pence(text: str) -> int:
    if not _AMOUNT.fullmatch(text or ""):
        raise QueueError("value_at_risk_gbp must be a plain number, zero or more")
    value = float(text)
    return math.floor(value * 100 + 0.5)


def parse_queue(text: str) -> list[Account]:
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != QUEUE_COLUMNS:
        raise QueueError("unexpected columns")
    accounts = [_account(row) for row in reader]
    if not accounts:
        raise QueueError("queue is empty")
    return sorted(accounts, key=lambda account: account.rank)


def _account(row: dict[str, str]) -> Account:
    if not _RANK.fullmatch(row["rank"] or "") or not row["customer_id"] or not row["primary_reason"]:
        raise QueueError("rank, customer_id and primary_reason are required")
    return Account(
        int(row["rank"]), row["customer_id"], to_pence(row["value_at_risk_gbp"]), row["primary_reason"], row["suggested_action"] or ""
    )


def by_reason(accounts: Sequence[Account]) -> list[tuple[str, int, int]]:
    """(reason, accounts, pence), largest group first, ties by name."""
    totals: dict[str, tuple[int, int]] = {}
    for account in accounts:
        count, pence = totals.get(account.primary_reason, (0, 0))
        totals = {**totals, account.primary_reason: (count + 1, pence + account.value_at_risk_pence)}
    return sorted(((name, count, pence) for name, (count, pence) in totals.items()), key=lambda item: (-item[1], item[0]))
