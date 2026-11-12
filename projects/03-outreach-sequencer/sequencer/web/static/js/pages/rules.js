import { api } from "../api.js";
import { fill, alertBox, field, h, icon, pageHead, toast, withBusy } from "../dom.js";

const DAYS = [[1, "Mon"], [2, "Tue"], [3, "Wed"], [4, "Thu"], [5, "Fri"], [6, "Sat"], [7, "Sun"]];
const STOP_LABELS = { replied: ["Stop when they reply", "The contact moves to Replied and no further steps are sent."], bounced: ["Stop when an email bounces", "The address is also added to the do-not-contact list."], meeting_booked: ["Stop when they book a meeting", "The contact moves to Meeting Booked."] };
const DEFAULTS = { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", email_per_day: 15, linkedin_invites_per_day: 8, linkedin_messages_per_day: 15, start_hour: 9, end_hour: 17, active_days: [1, 2, 3, 4, 5], stop_on: ["replied", "bounced", "meeting_booked"] };
const hour = (n) => `${String(n).padStart(2, "0")}:00`;

export async function render({ go, refresh }) {
  const cfg = await api.get("/api/config");
  let rules = { ...DEFAULTS, ...(cfg.rules ?? {}) };
  let sender = cfg.sender ?? { name: "", company: "", postal_address: "" };
  const errors = {};
  const summary = h("p", { class: "muted", "aria-live": "polite" });
  const status = h("div", { "aria-live": "polite" });

  const set = (patch) => { rules = { ...rules, ...patch }; paintSummary(); };
  const num = (key, label, max, hint) => field(label, h("input", { type: "number", min: 1, max, value: rules[key], onchange: (e) => set({ [key]: Math.trunc(Number(e.target.value)) }) }), hint);

  function paintSummary() {
    const days = DAYS.filter(([n]) => rules.active_days.includes(n)).map(([, d]) => d).join(", ") || "no days";
    summary.textContent = `Up to ${rules.email_per_day} emails, ${rules.linkedin_invites_per_day} invites and ${rules.linkedin_messages_per_day} LinkedIn messages a day, between ${hour(rules.start_hour)} and ${hour(rules.end_hour)} (${rules.timezone}) on ${days}. Sending stops for a contact when they ${rules.stop_on.length ? rules.stop_on.map((s) => ({ replied: "reply", bounced: "bounce", meeting_booked: "book a meeting" })[s]).join(", ") : "unsubscribe (only)"}${rules.stop_on.length ? ", or unsubscribe" : ""}.`;
  }

  async function save(btn) {
    await withBusy(btn, "Saving…", async () => {
      Object.keys(errors).forEach((k) => delete errors[k]);
      try {
        await api.post("/api/rules", rules);
        await api.post("/api/sender", sender);
        fill(status, alertBox("ok", "Saved. These apply the next time the sequence runs."));
        toast("Rules saved.");
        await refresh();
      } catch (e) { fill(status, alertBox("bad", e.message)); toast("Not saved. See the message at the bottom of the form.", "bad"); }
    });
  }

  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [DEFAULTS.timezone, "UTC"];
  const hourSelect = (key, from) => h("select", { onchange: (e) => set({ [key]: Number(e.target.value) }) }, Array.from({ length: from === 0 ? 24 : 24 }, (_, i) => i + (key === "end_hour" ? 1 : 0)).filter((n) => n <= 24).map((n) => h("option", { value: n, selected: n === rules[key] }, hour(n))));
  const L = cfg.limits;

  const page = h("div", { class: "stack" },
    pageHead("Step 5", "Set the sending rules", "These limits protect your mailbox and your LinkedIn account. They are ceilings, not targets, and a new LinkedIn account should start well below them.",
      h("button", { class: "btn btn-primary", type: "button", onclick: (e) => save(e.currentTarget) }, "Save rules")),
    h("div", { class: "card form-narrow" }, h("h2", {}, "Daily limits"),
      h("div", { class: "cols-3" }, num("email_per_day", "Emails per day", L.email, `Up to ${L.email}`), num("linkedin_invites_per_day", "Invites per day", L.invites, `Up to ${L.invites}`), num("linkedin_messages_per_day", "Messages per day", L.messages, `Up to ${L.messages}`)),
      alertBox("warn", "Automated LinkedIn activity can breach LinkedIn's terms and get an account restricted. Keep invites low, and raise them slowly.")),
    h("div", { class: "card form-narrow" }, h("h2", {}, "When to send"),
      h("div", { class: "cols-3" }, field("From", hourSelect("start_hour", 0)), field("Until", hourSelect("end_hour", 1)),
        field("Timezone", h("input", { type: "text", list: "zones", value: rules.timezone, onchange: (e) => set({ timezone: e.target.value.trim() }) }), "Start typing, for example Europe/London")),
      h("datalist", { id: "zones" }, zones.map((z) => h("option", { value: z }))),
      h("div", { role: "group", "aria-labelledby": "days-l" }, h("div", { class: "label", id: "days-l", style: "margin-bottom:8px" }, "Days"),
        h("div", { class: "days" }, DAYS.map(([n, d]) => h("button", { class: "chip day", type: "button", "aria-pressed": rules.active_days.includes(n), onclick: (e) => { const on = !rules.active_days.includes(n); e.currentTarget.setAttribute("aria-pressed", on); set({ active_days: on ? [...rules.active_days, n].sort() : rules.active_days.filter((x) => x !== n) }); } }, d))))),
    h("div", { class: "card form-narrow" }, h("h2", {}, "When to stop"),
      ...cfg.stop_kinds.map((k) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: rules.stop_on.includes(k), onchange: (e) => set({ stop_on: e.target.checked ? [...rules.stop_on, k] : rules.stop_on.filter((x) => x !== k) }) }), h("span", {}, h("b", {}, STOP_LABELS[k][0]), h("span", { class: "hint" }, STOP_LABELS[k][1])))),
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: true, disabled: true }), h("span", {}, h("b", {}, "Stop when they unsubscribe"), h("span", { class: "hint" }, h("span", {}, icon("lock")), " Always on. This is a legal requirement and can't be switched off.")))),
    h("div", { class: "card form-narrow" }, h("h2", {}, "Who the messages come from"),
      h("div", { class: "cols-2" }, field("Your name", h("input", { type: "text", value: sender.name, autocomplete: "name", onchange: (e) => { sender = { ...sender, name: e.target.value }; } })), field("Company", h("input", { type: "text", value: sender.company, onchange: (e) => { sender = { ...sender, company: e.target.value }; } }))),
      field("Postal address", h("input", { type: "text", value: sender.postal_address, onchange: (e) => { sender = { ...sender, postal_address: e.target.value }; } }), "Every email includes it with the opt-out line, as most anti-spam laws require.")),
    h("div", { class: "card form-narrow" }, h("h2", {}, "In plain words"), summary),
    status,
    h("div", { class: "row spread" }, h("span", {}), h("button", { class: "btn", type: "button", onclick: () => go("launch") }, "Next: launch", icon("arrow"))));
  paintSummary();
  return page;
}
