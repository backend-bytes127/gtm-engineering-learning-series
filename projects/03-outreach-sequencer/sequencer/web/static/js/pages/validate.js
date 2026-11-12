import { api } from "../api.js";
import { alertBox, badge, emptyState, h, pageHead, plural } from "../dom.js";

const REASONS = {
  invalid_email: ["Invalid email", "No usable email and no LinkedIn profile to fall back on."], duplicate: ["Duplicate", "Same person as an earlier row."],
  opted_out: ["Opted out", "On your do-not-contact list or marked unsubscribed."], no_reachable_channel: ["Unreachable", "No email and no LinkedIn URL."],
  missing_name: ["No name", "A message cannot be personalised without a name."],
};

export async function render({ state, go }) {
  if (!state.done.validate) {
    return h("div", {}, pageHead("Step 2", "Validate contacts"), emptyState("Nothing to validate yet", "Import a contact list first. Emails, LinkedIn URLs, duplicates and opt-outs are checked as part of the import.",
      h("button", { class: "btn btn-primary", type: "button", onclick: () => go("import") }, "Import contacts")));
  }
  const v = await api.get("/api/validation");
  const flagged = v.kept.filter((k) => k.flags.length);
  const read = v.kept.length + v.removed.length;
  let tab = v.removed.length ? "removed" : "kept", reason = null;
  const body = h("div", {});
  const tabs = h("div", { class: "tabs", role: "tablist" });

  const draw = () => {
    tabs.replaceChildren(...[["removed", "Removed", v.removed.length], ["flagged", "Kept with a note", flagged.length], ["kept", "All valid contacts", v.kept.length]].map(([id, label, n]) =>
      h("button", { class: "tab", role: "tab", "aria-selected": id === tab, onclick: () => { tab = id; reason = null; draw(); } }, label, h("span", { class: "count" }, n))));
    body.replaceChildren(tab === "removed" ? removedView() : keptView(tab === "flagged" ? flagged : v.kept));
  };

  const removedView = () => {
    const counts = Object.groupBy ? Object.entries(Object.groupBy(v.removed, (r) => r.reason)) : [];
    const rows = v.removed.filter((r) => !reason || r.reason === reason);
    return h("div", { class: "stack" },
      h("div", { class: "chips", role: "group", "aria-label": "Filter by reason" }, h("button", { class: "chip", "aria-pressed": reason === null, onclick: () => { reason = null; draw(); } }, `All ${v.removed.length}`),
        ...counts.map(([key, list]) => h("button", { class: "chip", "aria-pressed": reason === key, onclick: () => { reason = key; draw(); } }, `${REASONS[key]?.[0] ?? key} ${list.length}`))),
      rows.length === 0 ? emptyState("Nothing removed", "Every record passed the checks.") :
      h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Row", "Name", "Email", "Why it was removed"].map((t) => h("th", {}, t)))),
        h("tbody", {}, rows.map((r) => h("tr", {}, h("td", { class: "mono" }, r.row), h("td", {}, r.name || h("span", { class: "muted" }, "(no name)")), h("td", { class: "trunc" }, r.email),
          h("td", {}, badge(REASONS[r.reason]?.[0] ?? r.reason, "b-bad"), h("div", { class: "fine" }, r.detail))))))));
  };

  const keptView = (list) => list.length === 0 ? emptyState("Nothing here", "No contacts have notes.") :
    h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Row", "Name", "Company", "Email", "LinkedIn", "Notes"].map((t) => h("th", {}, t)))),
      h("tbody", {}, list.map((k) => h("tr", {}, h("td", { class: "mono" }, k.row), h("td", {}, k.name), h("td", {}, k.company || h("span", { class: "muted" }, "missing")), h("td", { class: "trunc" }, k.email || h("span", { class: "muted" }, "none")),
        h("td", {}, k.linkedin ? badge("yes", "b-ok") : h("span", { class: "muted" }, "none")), h("td", {}, k.flags.map((f) => h("div", { class: "fine" }, f))))))));

  draw();
  return h("div", { class: "stack" },
    pageHead("Step 2", "Validate contacts", "Every record was checked for a usable email, a real LinkedIn profile URL, duplicates and opt-outs. Removed records are kept here with the reason, nothing disappears silently.",
      h("button", { class: "btn btn-primary", type: "button", onclick: () => go("sequence") }, "Continue to sequence")),
    h("div", { class: "grid-kpi" }, [["Rows read", read], ["Valid", v.kept.length], ["Removed", v.removed.length], ["Kept with a note", flagged.length]].map(([l, n]) => h("div", { class: "kpi" }, h("span", {}, l), h("b", {}, n)))),
    alertBox("info", "Email checks are offline: they confirm an address is well formed and plausible (not disposable, not a typo like gmial.com), not that the mailbox exists. Confirming that needs a verification service."),
    h("div", { class: "card" }, tabs, body));
}
