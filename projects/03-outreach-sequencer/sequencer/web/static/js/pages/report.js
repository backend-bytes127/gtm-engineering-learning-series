import { api } from "../api.js";
import { alertBox, badge, emptyState, h, icon, pageHead, pct } from "../dom.js";

const rate = (n, d) => (d ? n / d : null);
const md = (text) => text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part) => (part.startsWith("**") ? h("b", {}, part.slice(2, -2)) : part.startsWith("`") ? h("span", { class: "mono" }, part.slice(1, -1)) : part));
const LABEL = { email: "Email", linkedin_invite: "LinkedIn invite", linkedin_message: "LinkedIn message", linkedin: "LinkedIn" };

export async function render({ state, go }) {
  if (!state.ran) {
    return h("div", {}, pageHead("Step 7", "Results"), emptyState("No results yet", "Launch a sequence and run it to see what was sent, opened, accepted, replied to and booked.",
      h("button", { class: "btn btn-primary", type: "button", onclick: () => go("launch") }, "Go to launch")));
  }
  const r = await api.get("/api/report");
  const m = r.metrics, c = m.contacts, sent = Object.values(m.by_channel).reduce((a, x) => a + x.sent, 0);

  const bar = (value, max = 1) => h("div", { class: "bar", style: "width:110px", role: "img", "aria-label": pct(value) }, h("i", { style: `width:${Math.min(100, ((value ?? 0) / max) * 100)}%;background:var(--accent)` }));
  const cell = (v) => (v == null ? h("span", { class: "muted", title: "Not applicable to this channel" }, "–") : v);
  const maxReply = Math.max(0.01, ...m.by_step.map((s) => rate(s.replied, s.sent) ?? 0));

  const stepRows = m.by_step.map((s) => {
    const email = s.channel === "email", inv = s.channel === "linkedin_invite";
    return h("tr", {}, h("td", {}, h("b", {}, s.step)), h("td", {}, LABEL[s.channel]), h("td", { class: "mono" }, s.template), h("td", { class: "r" }, s.sent), h("td", { class: "r" }, cell(email ? s.opened : null)), h("td", { class: "r" }, cell(inv ? s.accepted : null)),
      h("td", { class: "r" }, s.replied), h("td", { class: "r" }, s.meetings), h("td", {}, h("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" }, bar(rate(s.replied, s.sent), maxReply), h("span", { class: "num" }, pct(rate(s.replied, s.sent))))));
  });
  const channelCards = Object.entries(m.by_channel).map(([ch, x]) => h("div", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, LABEL[ch]), badge(`${x.sent} sent`)),
    h("div", { class: "grid-kpi", style: "grid-template-columns:repeat(auto-fit,minmax(110px,1fr))" },
      ...[ch === "email" ? ["Opened", x.opened, rate(x.opened, x.sent)] : ["Accepted", x.accepted, rate(x.accepted, x.sent)], ["Replied", x.replied, rate(x.replied, x.sent)], ["Meetings", x.meetings, rate(x.meetings, x.sent)]]
        .map(([l, n, p]) => h("div", {}, h("div", { class: "muted" }, l), h("b", { style: "font:600 26px var(--display)" }, n), h("div", { class: "fine" }, pct(p)))))));

  const removed = Object.entries(m.removed_by_reason), removedTotal = removed.reduce((a, [, n]) => a + n, 0);
  return h("div", { class: "stack" },
    pageHead("Step 7", "Results", "What was sent, by step and by channel, and what the numbers say.",
      h("a", { class: "btn btn-primary", href: "/api/report.xlsx", download: "Sequence_Report.xlsx" }, icon("download"), "Download Excel report")),
    r.simulated && alertBox("warn", h("span", {}, h("b", {}, "Simulated results. "), "Nothing was sent. These outcomes come from a seeded random model with made-up rates. Use them to see the shape of the report, not to plan a campaign.")),
    h("div", { class: "grid-kpi" }, [["Contacts launched", c.launched], ["Messages sent", sent], ["Contacts replied", c.replied], ["Meetings booked", c.meetings]].map(([l, n]) => h("div", { class: "kpi" }, h("span", {}, l), h("b", {}, n)))),
    h("div", { class: "card" }, h("h2", { style: "margin-bottom:12px" }, "What worked"), h("ul", { style: "margin:0;padding-left:20px;display:grid;gap:8px" }, r.summary.filter((l) => !l.startsWith("**Simulated")).map((l) => h("li", {}, md(l))))),
    h("div", { class: "card" }, h("h2", { style: "margin-bottom:12px" }, "By step"), h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Step", "Channel", "Message", "Sent", "Opened", "Accepted", "Replied", "Meetings", "Reply rate"].map((t, i) => h("th", { class: i >= 3 && i <= 7 ? "r" : "" }, t)))), h("tbody", {}, stepRows))),
      h("p", { class: "fine", style: "margin-top:10px" }, "A dash means the number doesn't exist for that channel: only emails are opened, and only invites are accepted. Opens depend on tracking pixels that many mail apps block, so trust replies and meetings more.")),
    h("div", { class: "cols-2" }, channelCards),
    removedTotal > 0 && h("div", { class: "card" }, h("h2", { style: "margin-bottom:12px" }, `Removed before sending (${removedTotal})`), h("div", { class: "chips" }, removed.map(([k, n]) => badge(`${k.replaceAll("_", " ")}: ${n}`)))));
}
