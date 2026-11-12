import { api } from "../api.js";
import { alertBox, badge, confirmDialog, h, icon, plural, toast, when, withBusy } from "../dom.js";

const RESULT = {
  not_connected: ["Invite, then message", "b-accent"], connected: ["Already connected: message only", "b-ok"], not_found: ["Profile not found", "b-bad"],
  no_linkedin: ["No LinkedIn URL", "b-bad"], self: ["This is you", "b-bad"],
};

// ---- before anything is sent: choose people, check them, start
export async function liveSetup(contacts, refresh) {
  const st = await api.get("/api/live");
  if (!st.configured) {
    return h("div", { class: "card form-narrow" }, h("h2", {}, "Send for real (LinkedIn)"),
      alertBox("info", "Not set up yet. Real sending needs a Unipile API key and account id in this app's environment (UNIPILE_API_KEY, UNIPILE_ACCOUNT_ID). Until then, use the simulation."));
  }
  const eligible = contacts.filter((c) => c.status === "In Sequence" && c.linkedin);
  const chosen = new Set();
  const results = h("div", { class: "stack" });
  const startBtn = h("button", { class: "btn btn-primary", type: "button", disabled: true, onclick: (e) => start(e.currentTarget) }, icon("play"), "Start sending to these contacts");
  const checkBtn = h("button", { class: "btn", type: "button", disabled: true, onclick: (e) => preflight(e.currentTarget) }, icon("search"), "Check these contacts first");
  let checked = false;

  const sync = () => { checkBtn.disabled = chosen.size === 0 || chosen.size > st.max_contacts; startBtn.disabled = !checked || chosen.size === 0; };
  async function preflight(btn) {
    await withBusy(btn, "Checking…", async () => {
      try {
        const r = await api.post("/api/live/preflight", { contacts: [...chosen] });
        results.replaceChildren(...r.contacts.map((c) => h("div", { class: "row spread" }, h("div", {}, h("b", {}, c.name), h("div", { class: "fine" }, c.note)), badge(RESULT[c.result]?.[0] ?? c.result, RESULT[c.result]?.[1] ?? ""))));
        checked = r.contacts.every((c) => ["connected", "not_connected"].includes(c.result));
        if (!checked) results.append(alertBox("warn", "Fix or uncheck the contacts marked in red before starting."));
        sync();
      } catch (e) { toast(e.message, "bad"); }
    });
  }
  async function start(btn) {
    const ok = await confirmDialog({ title: `Send real LinkedIn messages to ${plural(chosen.size, "person", "people")}?`,
      body: `These are real invites and messages from your LinkedIn account. Limits: ${st.caps.invites} invites and ${st.caps.messages} messages a day. You can stop at any time.`, confirmLabel: "Start sending" });
    if (!ok) return;
    await withBusy(btn, "Starting…", async () => {
      try { await api.post("/api/live/start", { contacts: [...chosen], confirm: true }); toast("Live sending started."); await refresh(); } catch (e) { toast(e.message, "bad"); }
    });
  }

  return h("div", { class: "card form-narrow" }, h("h2", {}, "Send for real (LinkedIn)"),
    alertBox("warn", `This sends from your own LinkedIn account. Pick a few people who know you. At most ${st.max_contacts} at a time, ${st.caps.invites} invites and ${st.caps.messages} messages a day. Automated LinkedIn activity can get an account restricted.`),
    eligible.length === 0 ? h("p", { class: "muted" }, "No contacts in the sequence have a LinkedIn URL.") :
    h("fieldset", { style: "border:0;padding:0;margin:0;display:grid;gap:8px;max-height:260px;overflow:auto" }, h("legend", { class: "label", style: "margin-bottom:8px" }, "Who to send to"),
      ...eligible.map((c) => h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => { e.target.checked ? chosen.add(c.key) : chosen.delete(c.key); checked = false; startBtn.disabled = true; results.replaceChildren(); sync(); } }),
        h("span", {}, h("b", {}, c.name), h("span", { class: "hint" }, c.company || "")))),
    ),
    results, h("div", { class: "row" }, checkBtn, startBtn),
    st.webhook_secret_set ? null : h("p", { class: "fine" }, "Replies are picked up by webhook. Set UNIPILE_WEBHOOK_SECRET and register this app's /api/webhooks/unipile URL in Unipile, otherwise replies will not appear."));
}

// ---- while it is running: status and the stop switch
export async function livePanel(refresh, contacts) {
  const st = await api.get("/api/live");
  const last = st.status;
  const stop = async (btn) => { await withBusy(btn, "Stopping…", async () => { try { await api.post("/api/live/stop"); toast("Sending stopped."); await refresh(); } catch (e) { toast(e.message, "bad"); } }); };
  const resume = async (btn) => { await withBusy(btn, "Resuming…", async () => { try { await api.post("/api/live/start", { contacts: st.contacts.map((c) => c.key), confirm: true }); toast("Sending resumed."); await refresh(); } catch (e) { toast(e.message, "bad"); } }); };
  return h("div", { class: "card stack" },
    h("div", { class: "card-head" }, h("h2", {}, "Live sending"), st.enabled ? badge("Running", "b-ok") : badge("Stopped", "b-bad")),
    alertBox(st.enabled ? "warn" : "info", st.enabled ? "Real messages are being sent from your LinkedIn account to the people below." : "Nothing is being sent."),
    h("div", { class: "row" }, st.contacts.map((c) => badge(`${c.name}: ${c.status}`))),
    last && h("p", { class: "muted" }, `Last check ${when(last.at)}: ${plural(last.sent ?? 0, "message")} sent${last.window_closed ? `, outside sending hours (${last.window_closed.replaceAll("_", " ")})` : ""}${last.deferred_limit ? `, ${last.deferred_limit} waiting on the daily limit` : ""}.`),
    last?.error && alertBox("bad", `Last error: ${last.error}`),
    !st.webhook_secret_set && alertBox("warn", "Replies will not appear: UNIPILE_WEBHOOK_SECRET is not set."),
    h("div", { class: "row" }, st.enabled ? h("button", { class: "btn btn-danger", type: "button", onclick: (e) => stop(e.currentTarget) }, "Stop sending") : h("button", { class: "btn", type: "button", onclick: (e) => resume(e.currentTarget) }, "Resume sending")));
}
