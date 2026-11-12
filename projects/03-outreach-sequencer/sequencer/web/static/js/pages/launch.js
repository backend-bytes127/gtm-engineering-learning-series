import { api } from "../api.js";
import { livePanel, liveSetup } from "./live.js";
import { fill, alertBox, badge, confirmDialog, emptyState, field, h, icon, openDrawer, pageHead, plural, statusBadge, stopLabel, toast, when, withBusy, CHANNEL } from "../dom.js";

const FIX = { "Contacts imported and validated": "import", "Sequence is well-formed": "sequence", "Every template approved": "messages", "Every draft personalised and within channel limits": "validate", "Sender profile set": "rules", "Sending limits, hours and stop rules set": "rules" };
const EVENTS = [["replied", "Replied"], ["meeting_booked", "Meeting booked"], ["accepted", "Invite accepted"], ["bounced", "Bounced"], ["unsubscribed", "Unsubscribed"]];

export async function render({ state, go, refresh }) {
  const cfg = await api.get("/api/config");
  const names = cfg.sequences.map((s) => s.name);
  if (!names.length) return h("div", {}, pageHead("Step 6", "Launch and track"), emptyState("Build a sequence first", "Launch needs a sequence, approved messages and sending rules.", h("button", { class: "btn btn-primary", type: "button", onclick: () => go("sequence") }, "Build a sequence")));
  const wanted = decodeURIComponent(location.hash.split("?")[1] ?? "");
  const name = state.live[0] ?? (names.includes(wanted) ? wanted : names[0]);
  const [check, list] = await Promise.all([api.get(`/api/launch/check?sequence=${encodeURIComponent(name)}`), api.get("/api/contacts")]);
  return h("div", { class: "stack" }, state.live.length ? await live(state, list.contacts, refresh, name) : gate(name, names, check, go, refresh));
}

// ---------------------------------------------------------------- before launch: the gate
function gate(name, names, check, go, refresh) {
  let chosen = name;
  const launch = async (btn, hold) => {
    if (!(await confirmDialog({ title: `Launch “${chosen}”?`, body: hold ? `${plural(check.incomplete.length, "contact")} will be held back because a message can't be personalised. Everyone else enters the sequence.` : "Every valid contact enters the sequence. Launching sends nothing: you choose next whether to run the simulation or send for real.", confirmLabel: "Launch" }))) return;
    await withBusy(btn, "Launching…", async () => {
      try { const r = await api.post("/api/launch", { sequence: chosen, hold_incomplete: hold }); toast(`${plural(r.launched, "contact")} entered the sequence.`); await refresh(); } catch (e) { toast(e.message, "bad"); }
    });
  };
  const items = check.items.map((i) => h("div", { class: "chk" }, h("span", { class: `chk-ic ${i.ok ? "" : "no"}` }, icon(i.ok ? "check" : "x")),
    h("div", {}, h("b", {}, i.label), h("div", { class: "muted" }, i.detail)), !i.ok && FIX[i.label] && h("button", { class: "btn btn-sm", type: "button", onclick: () => go(FIX[i.label]) }, "Fix", icon("arrow"))));
  return h("div", { class: "stack" },
    pageHead("Step 6", "Launch and track", "Nothing goes live until every check passes. This is the last stop before contacts enter the sequence."),
    names.length > 1 && field("Sequence", h("select", { onchange: (e) => go(`launch?${encodeURIComponent(e.target.value)}`) }, names.map((n) => h("option", { value: n, selected: n === name }, n)))),
    h("div", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, `Launch checklist: ${name}`), check.ready ? badge("Ready", "b-ok") : badge(`${check.items.filter((i) => !i.ok).length} to fix`, "b-bad")), h("div", { class: "chk-list" }, items)),
    check.incomplete.length > 0 && h("div", { class: "card" }, h("h2", { style: "margin-bottom:8px" }, `${plural(check.incomplete.length, "contact")} can't be personalised`),
      h("p", { class: "muted" }, "A message would go out with an empty gap, for example “Hi Sam, how is  doing?”. Fix the data, or hold these contacts back."),
      h("ul", {}, check.incomplete.map((c) => h("li", {}, h("span", { class: "mono" }, c.key), ": missing ", [...new Set(c.problems.map((p) => p.replace(/^step \d+: /, "")))].join(", "))))),
    h("div", { class: "row" },
      h("button", { class: "btn btn-primary", type: "button", disabled: !check.ready, onclick: (e) => launch(e.currentTarget, false), title: check.ready ? "" : "Fix the items above first" }, icon("play"), "Launch sequence"),
      check.can_hold && h("button", { class: "btn", type: "button", onclick: (e) => launch(e.currentTarget, true) }, `Launch, holding back ${check.incomplete.length}`),
      !check.ready && !check.can_hold && h("span", { class: "fine" }, "The launch button unlocks when every check passes.")));
}

// ---------------------------------------------------------------- after launch: run, track
async function live(state, contacts, refresh, name) {
  const body = h("div", { class: "stack" });
  const head = pageHead("Step 6", "Launch and track", "Contacts move through the steps on schedule. Open a contact to see every touch, or record what happened.");
  if (!state.ran) {
    const days = h("input", { type: "number", min: 1, max: 120, value: 60 }), seed = h("input", { type: "number", value: 7 });
    const run = async (btn) => withBusy(btn, "Running…", async () => {
      try { const r = await api.post("/api/run", { days: Number(days.value), seed: Number(seed.value) }); toast(`Simulated ${r.days} days: ${r.touches_sent} messages sent.`); await refresh(); } catch (e) { toast(e.message, "bad"); }
    });
    return h("div", { class: "stack" }, head, alertBox("ok", `“${name}” is live: ${plural(state.counts["In Sequence"], "contact")} in sequence.`),
      h("div", { class: "card form-narrow" }, h("h2", {}, "Run the sequence"),
        alertBox("info", h("span", {}, h("b", {}, "Simulated. "), "Nothing is sent. Replies, bounces and meetings are generated from a seeded random model with made-up rates, so you can watch every rule work. Real sending needs a mailbox and LinkedIn provider connected.")),
        h("div", { class: "cols-2" }, field("Days to simulate", days, "The clock jumps hour by hour; sending hours and limits apply."), field("Random seed", seed, "The same seed gives the same outcome.")),
        h("div", { class: "row" }, h("button", { class: "btn btn-primary", type: "button", onclick: (e) => run(e.currentTarget) }, icon("play"), "Run simulation"), h("button", { class: "btn btn-quiet", type: "button", onclick: () => resetRun(refresh) }, "Back out and edit"))), await liveSetup(contacts, refresh));
  }
  const counts = state.counts, total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  const COLORS = { "Meeting Booked": "var(--ok)", Replied: "color-mix(in srgb, var(--ok) 60%, var(--surface))", "In Sequence": "var(--accent)", Completed: "var(--line-strong)", Stopped: "var(--bad)", "Not Started": "var(--neutral-soft)" };
  let query = "", filter = null;
  const table = h("div", {});
  const paint = () => {
    const rows = contacts.filter((c) => (!filter || c.status === filter) && (!query || `${c.name} ${c.company} ${c.email}`.toLowerCase().includes(query.toLowerCase())));
    fill(table, rows.length === 0 ? emptyState("No contacts match", "Try a different search or filter.") :
      h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Contact", "Company", "Status", "Touches", "Next"].map((t, i) => h("th", { class: i === 3 ? "r" : "" }, t)))),
        h("tbody", {}, rows.map((c) => h("tr", { class: "click", tabindex: 0, onclick: () => detail(c.key, refresh), onkeydown: (e) => e.key === "Enter" && detail(c.key, refresh) },
          h("td", {}, h("b", {}, c.name), h("div", { class: "fine mono" }, c.key)), h("td", {}, c.company || h("span", { class: "muted" }, "none")),
          h("td", {}, statusBadge(c.status), c.stop_reason && h("div", { class: "fine" }, stopLabel(c.stop_reason))), h("td", { class: "r" }, c.sent), h("td", { class: "fine" }, c.next_due ? `Step ${c.next_step}, ${when(c.next_due)}` : "")))))));
  };
  paint();
  return h("div", { class: "stack" }, head, state.simulated ? alertBox("info", h("span", {}, h("b", {}, "Simulated results. "), "These outcomes come from a seeded random model, not from real sending.")) : await livePanel(refresh, contacts),
    h("div", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, "Where everyone is"), h("button", { class: "btn btn-sm", type: "button", onclick: () => resetRun(refresh) }, icon("reset"), "Reset results")),
      h("div", { class: "bar", role: "img", "aria-label": Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(", ") }, Object.entries(counts).filter(([, v]) => v).map(([k, v]) => h("i", { style: `width:${(v / total) * 100}%;background:${COLORS[k]}`, title: `${k}: ${v}` }))),
      h("div", { class: "chips", style: "margin-top:14px" }, h("button", { class: "chip", "aria-pressed": filter === null, onclick: () => { filter = null; setPressed(); paint(); } }, `All ${total}`),
        ...Object.entries(counts).filter(([, v]) => v).map(([k, v]) => h("button", { class: "chip", "aria-pressed": filter === k, dataset: { f: k }, onclick: () => { filter = filter === k ? null : k; setPressed(); paint(); } }, `${k} ${v}`)))),
    h("div", { class: "card stack" }, field("Search contacts", h("input", { type: "text", placeholder: "Name, company or email", oninput: (e) => { query = e.target.value; paint(); } })), table),
    h("div", { class: "row spread" }, h("span", {}), h("a", { class: "btn btn-primary", href: "#/report" }, "See the report", icon("arrow"))));
  function setPressed() { document.querySelectorAll(".chip[data-f], .chips .chip:first-child").forEach((c) => c.setAttribute("aria-pressed", (c.dataset.f ?? null) === filter)); }
}

async function resetRun(refresh) {
  if (!(await confirmDialog({ title: "Reset the results?", body: "All touches and replies are cleared and everyone goes back to Not Started. Your list and messages stay.", confirmLabel: "Reset results", danger: true }))) return;
  try { await api.post("/api/reset", { scope: "run" }); toast("Results cleared."); await refresh(); } catch (e) { toast(e.message, "bad"); }
}

async function detail(key, refresh) {
  const d = await api.get(`/api/contacts/${key}`);
  const c = d.contact;
  const content = h("div", { class: "stack" });
  const paint = (data) => {
    fill(content, 
      h("div", { class: "row" }, statusBadge(data.contact.status), data.contact.stop_reason && badge(stopLabel(data.contact.stop_reason), "b-bad")),
      h("div", { class: "muted" }, [data.contact.title, data.contact.company].filter(Boolean).join(", ")),
      h("div", { class: "fine" }, [data.contact.email, data.contact.linkedin].filter(Boolean).join("  ·  ")),
      h("div", {}, h("div", { class: "label", style: "margin-bottom:8px" }, "Record what happened"), h("div", { class: "chips" }, EVENTS.map(([kind, label]) => h("button", { class: "chip", type: "button", onclick: async () => {
        try { const r = await api.post("/api/event", { contact: key, kind }); toast(r.recorded ? `${label}. Status is now ${r.status}.` : "Already recorded."); paint(await api.get(`/api/contacts/${key}`)); refresh(); } catch (e) { toast(e.message, "bad"); } } }, label)))),
      data.touches.length === 0 ? h("p", { class: "muted" }, "Nothing has happened for this contact yet.") :
      h("div", { class: "timeline" }, data.touches.map((t) => h("div", { class: "t-item" }, h("div", { class: `t-dot ${t.status === "skipped" ? "skip" : t.status === "failed" ? "fail" : ""}` }, icon(CHANNEL[t.channel]?.icon ?? "info")),
        h("div", {}, h("div", { class: "row" }, h("b", {}, `Step ${t.step}: ${CHANNEL[t.channel]?.label ?? t.channel}`), t.status !== "sent" && badge(t.status === "skipped" ? `Skipped: ${t.reason.replaceAll("_", " ")}` : "Failed", t.status === "failed" ? "b-bad" : ""), ...t.events.map((e) => badge(e.replaceAll("_", " "), "b-ok"))),
          h("div", { class: "fine" }, when(t.at)), t.subject && h("div", { style: "margin-top:6px;font-weight:600" }, t.subject), t.body && h("div", { class: "preview", style: "margin-top:6px;padding:12px" }, h("div", { class: "body" }, t.body)))))));
  };
  openDrawer(c.name, c.key, content);
  paint(d);
}
