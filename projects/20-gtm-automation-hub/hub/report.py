"""Write the offline simulation report and chart. Synthetic payloads only."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from hub.churn import Account, by_reason  # noqa: E402
from hub.messages import pounds  # noqa: E402
from hub.simulate import Observation  # noqa: E402


def posted(observation: Observation) -> int:
    return sum(1 for post in observation.posts if post["status"] == 200)


def markdown(observations: Sequence[Observation], accounts: Sequence[Account], as_of: str, digest_day: date) -> str:
    matched = sum(o.matched for o in observations)
    lines = [
        "# Offline simulation report",
        "",
        "Every payload here is **synthetic**. This is the Python reference, with an in-memory Slack. It does not call n8n or Slack.",
        "The same webhook steps are run against n8n by `e2e/run_e2e.py`; see `reports/e2e.md`.",
        "",
        f"**{matched} of {len(observations)} webhook steps gave the expected status and outcome.**",
        "",
        "| # | Route | Step | HTTP | Outcome | Posts accepted / tried |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {i} | {o.step.route} | {o.step.name} | {o.status} | `{o.outcome}` | {posted(o)} / {len(o.posts)} |"
        for i, o in enumerate(observations, 1)
    ]
    total = sum(a.value_at_risk_pence for a in accounts)
    lines += ["", f"## Churn digest input (invented, file dated {as_of})", ""]
    lines += [f"{len(accounts)} accounts, {pounds(total)} score-weighted trailing revenue. Digest built for {digest_day}.", ""]
    lines += ["| Primary reason | Accounts | Score-weighted revenue |", "|---|---|---|"]
    lines += [f"| {name} | {count} | {pounds(pence)} |" for name, count, pence in by_reason(accounts)]
    return "\n".join(lines) + "\n"


def chart(observations: Sequence[Observation], target: Path) -> None:
    counts = Counter(f"{o.step.route}: {o.outcome}" for o in observations)
    labels = sorted(counts, reverse=True)
    figure, axis = plt.subplots(figsize=(9, 0.32 * len(labels) + 1.2))
    axis.barh(labels, [counts[label] for label in labels], color="#1e3a5f")
    axis.set_xlabel("steps in the scripted tour (synthetic; not a traffic measurement)")
    axis.set_title("Which outcomes the offline tour exercises")
    axis.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    figure.tight_layout()
    figure.savefig(target, dpi=130)
    plt.close(figure)


def write(observations: Sequence[Observation], accounts: Sequence[Account], as_of: str, digest_day: date, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.md").write_text(markdown(observations, accounts, as_of, digest_day), encoding="utf-8")
    chart(observations, directory / "outcomes.png")
