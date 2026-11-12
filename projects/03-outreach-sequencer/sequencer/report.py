"""Step 7: report by step and by channel (sent, opened, accepted, replied, meetings) and say what worked.

Counts are of *messages* (a touch counts once however many times it was opened), except the contact-level
numbers, which count people. The "what worked" text compares channels or steps only when there are enough
messages to compare; otherwise it says so instead of declaring a winner.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from . import constants as C
from .store import Store

CONVERSATION_STEP = 1000  # touches at or above this step number are AI conversation replies, not sequence steps
MIN_SAMPLE = 20  # messages per group before two groups are compared
MIN_REPLIES = 10  # replies across both groups before a gap between them means anything


@dataclass(frozen=True)
class Metrics:
    sent: int = 0
    opened: int = 0
    accepted: int = 0
    replied: int = 0
    meetings: int = 0

    def _rate(self, n: int) -> float | None:
        return n / self.sent if self.sent else None

    @property
    def open_rate(self) -> float | None:
        return self._rate(self.opened)

    @property
    def accept_rate(self) -> float | None:
        return self._rate(self.accepted)

    @property
    def reply_rate(self) -> float | None:
        return self._rate(self.replied)

    @property
    def meeting_rate(self) -> float | None:
        return self._rate(self.meetings)

    def plus(self, other: Metrics) -> Metrics:
        return Metrics(*(a + b for a, b in zip(self.__dict__.values(), other.__dict__.values(), strict=True)))


@dataclass(frozen=True)
class StepStat:
    sequence: str
    step: int
    channel: str
    template: str
    metrics: Metrics


@dataclass(frozen=True)
class ChannelStat:
    channel: str  # "email" or "linkedin"
    metrics: Metrics


@dataclass(frozen=True)
class Report:
    by_step: list[StepStat]
    by_channel: list[ChannelStat]
    statuses: Counter
    stop_reasons: dict[str, int]
    removed_by_reason: dict[str, int]
    contacts_total: int
    contacts_launched: int
    contacts_held: int
    contacts_replied: int
    contacts_meeting: int
    contacts_bounced: int
    contacts_email_reached: int
    first_reply_by_step: dict[int, int]


def _touch_metrics(kinds: set[str]) -> Metrics:
    return Metrics(
        sent=1,
        opened=int(C.OPENED in kinds),
        accepted=int(C.ACCEPTED in kinds),
        replied=int(C.REPLY in kinds),
        meetings=int(C.MEETING in kinds),
    )


def build_report(store: Store) -> Report:
    touches = [t for t in store.touches() if t.status == C.SENT and t.step < CONVERSATION_STEP]
    events = store.events()
    kinds_by_touch: dict[int, set[str]] = {}
    for e in events:
        if e.touch_id is not None:
            kinds_by_touch.setdefault(e.touch_id, set()).add(e.kind)

    step_metrics: dict[tuple[str, int, str, str], Metrics] = {}
    channel_metrics: dict[str, Metrics] = {}
    for t in touches:
        m = _touch_metrics(kinds_by_touch.get(t.id, set()))
        key = (t.sequence, t.step, t.channel, t.template_id)
        step_metrics[key] = step_metrics.get(key, Metrics()).plus(m)
        group = C.CHANNEL_GROUP[t.channel]
        channel_metrics[group] = channel_metrics.get(group, Metrics()).plus(m)

    contacts = store.contacts()
    launched = [c for c in contacts if c.status != C.NOT_STARTED and c.stop_reason != C.REASON_DRAFT_INCOMPLETE]
    first_reply: dict[str, int | None] = {}
    for e in events:
        if e.kind == C.REPLY and e.contact_key not in first_reply:
            touch = next((t for t in touches if t.id == e.touch_id), None)
            first_reply[e.contact_key] = touch.step if touch else None
    attributed = Counter(step for step in first_reply.values() if step is not None)
    removed = Counter(r.reason for r in store.removed())
    ordered = [GROUP for GROUP in ("email", "linkedin") if GROUP in channel_metrics]
    email_reached = {t.contact_key for t in touches if t.channel == C.EMAIL}
    return Report(
        by_step=[
            StepStat(k[0], k[1], k[2], k[3], m) for k, m in sorted(step_metrics.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        ],
        by_channel=[ChannelStat(g, channel_metrics[g]) for g in ordered],
        statuses=Counter(c.status for c in contacts),
        stop_reasons=dict(Counter(c.stop_reason for c in contacts if c.stop_reason)),
        removed_by_reason=dict(removed),
        contacts_total=len(contacts),
        contacts_launched=len(launched),
        contacts_held=sum(1 for c in contacts if c.stop_reason == C.REASON_DRAFT_INCOMPLETE),
        contacts_replied=len({e.contact_key for e in events if e.kind == C.REPLY}),
        contacts_meeting=len({e.contact_key for e in events if e.kind == C.MEETING}),
        contacts_bounced=len({e.contact_key for e in events if e.kind == C.BOUNCED}),
        contacts_email_reached=len(email_reached),
        first_reply_by_step=dict(sorted(attributed.items())),
    )


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _label(channel: str) -> str:
    return {
        "email": "email",
        "linkedin": "LinkedIn",
        C.LINKEDIN_INVITE: "LinkedIn invite",
        C.LINKEDIN_MESSAGE: "LinkedIn message",
    }.get(channel, channel)


def summary_lines(r: Report, simulated: bool) -> list[str]:
    """Plain-language findings. Every claim carries its count so the reader can judge the sample."""
    lines: list[str] = []
    if simulated:
        lines.append(
            "**Simulated results.** Nothing was sent. Outcomes come from a seeded random model with made-up rates, "
            "so use this report to see its shape, not to plan a campaign."
        )
    sent = {c.channel: c.metrics.sent for c in r.by_channel}
    total_sent = sum(sent.values())
    lines.append(
        f"{r.contacts_launched} contacts entered the sequence and {total_sent} messages were sent "
        f"({sent.get('email', 0)} email, {sent.get('linkedin', 0)} LinkedIn)."
    )
    if r.contacts_held:
        lines.append(f"{r.contacts_held} contact(s) were held back before launch because a message could not be personalised.")
    if r.contacts_launched:
        lines.append(
            f"{r.contacts_replied} of {r.contacts_launched} contacts replied ({_pct(r.contacts_replied / r.contacts_launched)}) "
            f"and {r.contacts_meeting} booked a meeting."
        )

    chans = {c.channel: c.metrics for c in r.by_channel}
    if "email" in chans and "linkedin" in chans:
        e, li = chans["email"], chans["linkedin"]
        if min(e.sent, li.sent) < MIN_SAMPLE:
            lines.append(
                f"Channel comparison: fewer than {MIN_SAMPLE} messages on one channel "
                f"({e.sent} email, {li.sent} LinkedIn), too few to say which channel works better."
            )
        elif e.replied + li.replied < MIN_REPLIES:
            lines.append(
                f"Channel comparison: only {e.replied + li.replied} replies in all ({e.replied} email, {li.replied} LinkedIn); "
                f"a gap that small is noise, so no channel is called better."
            )
        elif (e.reply_rate or 0) == (li.reply_rate or 0):
            lines.append(f"Email and LinkedIn replied at the same rate ({_pct(e.reply_rate)}).")
        else:
            linkedin_wins = (li.reply_rate or 0) > (e.reply_rate or 0)
            better, other = ("LinkedIn", "email") if linkedin_wins else ("Email", "LinkedIn")
            hi, lo = (li, e) if linkedin_wins else (e, li)
            lines.append(
                f"{better} replied more often: {_pct(hi.reply_rate)} of {hi.sent} messages "
                f"against {_pct(lo.reply_rate)} of {lo.sent} for {other}."
            )

    invites = [s for s in r.by_step if s.channel == C.LINKEDIN_INVITE]
    for s in invites:
        lines.append(
            f"LinkedIn invites (step {s.step}): {s.metrics.accepted} of {s.metrics.sent} accepted "
            f"({_pct(s.metrics.accept_rate)})."
        )

    if r.first_reply_by_step:
        total = sum(r.first_reply_by_step.values())
        top = max(r.first_reply_by_step.values())
        leaders = sorted(step for step, n in r.first_reply_by_step.items() if n == top)
        if len(leaders) > 1:
            lines.append(
                f"First replies were split evenly between steps {', '.join(map(str, leaders))} " f"({top} each, {total} in all)."
            )
        else:
            stat = next(s for s in r.by_step if s.step == leaders[0])
            lines.append(
                f"Most first replies came from step {leaders[0]} ({_label(stat.channel)}, "
                f"template `{stat.template}`): {top} of {total}."
            )
    silent = [s for s in r.by_step if s.channel != C.LINKEDIN_INVITE and s.metrics.sent >= MIN_SAMPLE and s.metrics.replied == 0]
    for s in silent:
        lines.append(
            f"Step {s.step} (`{s.template}`) got no replies from {s.metrics.sent} messages; consider rewriting or cutting it."
        )

    if r.contacts_email_reached:
        lines.append(
            f"List hygiene: {r.contacts_bounced} of {r.contacts_email_reached} emailed contacts bounced"
            + ("; verify addresses with an SMTP-level checker before the next send." if r.contacts_bounced else ".")
        )
    opt_out = r.stop_reasons.get(C.REASON_OPTED_OUT, 0)
    if opt_out:
        lines.append(f"{opt_out} contact(s) unsubscribed and are now on the suppression list.")
    return lines


# ----------------------------------------------------------------------------------------------- output files

FORMULA_STARTS = ("=", "+", "-", "@")
METRIC_HEADER = ["Sent", "Opened", "Accepted", "Replied", "Meetings", "Open rate", "Accept rate", "Reply rate", "Meeting rate"]


def _metric_cells(m: Metrics, channel: str) -> list:
    """Opens only exist for email and accepts only for invites, so the other cells are blank rather than a misleading 0."""
    email = channel in (C.EMAIL, "email")
    linkedin = channel in (C.LINKEDIN_INVITE, "linkedin")  # only invites are accepted; a DM is not
    opened, open_rate = (m.opened, m.open_rate) if email else (None, None)
    accepted, accept_rate = (m.accepted, m.accept_rate) if linkedin else (None, None)
    return [m.sent, opened, accepted, m.replied, m.meetings, open_rate, accept_rate, m.reply_rate, m.meeting_rate]


def write_markdown(r: Report, path: str | Path, simulated: bool) -> None:
    def row(cells: list) -> str:
        return "| " + " | ".join("" if c is None else (f"{c:.0%}" if isinstance(c, float) else str(c)) for c in cells) + " |"

    head = ["Step", "Channel", "Template", *METRIC_HEADER]
    out = [
        "# Sequence results",
        "",
        "## What worked",
        "",
        *[f"- {line}" for line in summary_lines(r, simulated)],
        "",
        "## By step",
        "",
    ]
    out += [row(head), row(["---"] * len(head))]
    out += [row([s.step, _label(s.channel), s.template, *_metric_cells(s.metrics, s.channel)]) for s in r.by_step]
    out += ["", "## By channel", "", row(["Channel", *METRIC_HEADER]), row(["---"] * (len(METRIC_HEADER) + 1))]
    out += [row([_label(c.channel), *_metric_cells(c.metrics, c.channel)]) for c in r.by_channel]
    out += ["", "## Contact status", "", row(["Status", "Contacts"]), row(["---", "---"])]
    out += [row([s, r.statuses.get(s, 0)]) for s in C.STATUSES]
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def _sheet(wb: openpyxl.Workbook, title: str, header: list[str], rows: list[list], first: bool = False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str) and cell.value[:1] in FORMULA_STARTS:
                cell.data_type = "s"  # contact data is untrusted: text such as =HYPERLINK(...) must stay text, not run in Excel
    ws.freeze_panes = "A2"
    for i, _ in enumerate(header, start=1):
        width = max(len(str(c.value)) if c.value is not None else 0 for c in ws[get_column_letter(i)])
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)
    for col in ws.iter_cols(min_row=2):
        for cell in col:
            if isinstance(cell.value, float):
                cell.number_format = "0%"
    return ws


def write_xlsx(store: Store, r: Report, path: str | Path, simulated: bool) -> None:
    wb = openpyxl.Workbook()
    _sheet(
        wb,
        "Summary",
        ["What worked"],
        [[line.replace("**", "").replace("`", "")] for line in summary_lines(r, simulated)],
        first=True,
    )
    wb["Summary"].column_dimensions["A"].width = 140
    _sheet(
        wb,
        "By Step",
        ["Sequence", "Step", "Channel", "Template", *METRIC_HEADER],
        [[s.sequence, s.step, s.channel, s.template, *_metric_cells(s.metrics, s.channel)] for s in r.by_step],
    )
    _sheet(
        wb,
        "By Channel",
        ["Channel", *METRIC_HEADER],
        [[_label(c.channel), *_metric_cells(c.metrics, c.channel)] for c in r.by_channel],
    )

    touches = store.touches()
    events_by_touch: dict[int, list[str]] = {}
    for e in store.events():
        if e.touch_id is not None:
            events_by_touch.setdefault(e.touch_id, []).append(e.kind)
    contact_rows = []
    for t in store.contacts():
        sent = [x for x in touches if x.contact_key == t.contact.key and x.status == C.SENT]
        last = sent[-1] if sent else None
        c = t.contact
        contact_rows.append(
            [
                c.key,
                c.name,
                c.company,
                c.email,
                c.linkedin_url,
                c.sequence,
                t.status,
                t.stop_reason,
                len(sent),
                f"step {last.step} {last.channel}" if last else "",
                last.at.strftime("%Y-%m-%d %H:%M") if last else "",
            ]
        )
    _sheet(
        wb,
        "Contacts",
        [
            "Key",
            "Name",
            "Company",
            "Email",
            "LinkedIn",
            "Sequence",
            "Status",
            "Stop reason",
            "Messages sent",
            "Last touch",
            "Last touch at (UTC)",
        ],
        contact_rows,
    )
    _sheet(
        wb,
        "Touch Log",
        ["Date (UTC)", "Contact", "Sequence", "Step", "Channel", "Template", "Outcome", "Reason", "Events"],
        [
            [
                t.at.strftime("%Y-%m-%d %H:%M"),
                t.contact_key,
                t.sequence,
                t.step,
                t.channel,
                t.template_id,
                t.status,
                t.reason,
                ", ".join(events_by_touch.get(t.id, [])),
            ]
            for t in touches
        ],
    )
    _sheet(
        wb,
        "Removed Records",
        ["Source row", "Name", "Email", "LinkedIn", "Reason", "Detail"],
        [[x.contact.row, x.contact.name, x.contact.email, x.contact.linkedin_url, x.reason, x.detail] for x in store.removed()],
    )
    wb.save(path)


def metrics_dict(r: Report) -> dict:
    """The numbers behind the report as plain data, used for the golden-file check."""

    def m(x: Metrics) -> dict:
        return {"sent": x.sent, "opened": x.opened, "accepted": x.accepted, "replied": x.replied, "meetings": x.meetings}

    return {
        "contacts": {
            "total": r.contacts_total,
            "launched": r.contacts_launched,
            "replied": r.contacts_replied,
            "meetings": r.contacts_meeting,
            "bounced": r.contacts_bounced,
        },
        "statuses": {s: r.statuses.get(s, 0) for s in C.STATUSES},
        "stop_reasons": dict(sorted(r.stop_reasons.items())),
        "removed_by_reason": dict(sorted(r.removed_by_reason.items())),
        "by_step": [{"step": s.step, "channel": s.channel, "template": s.template, **m(s.metrics)} for s in r.by_step],
        "by_channel": {c.channel: m(c.metrics) for c in r.by_channel},
        "first_reply_by_step": {str(k): v for k, v in r.first_reply_by_step.items()},
    }
