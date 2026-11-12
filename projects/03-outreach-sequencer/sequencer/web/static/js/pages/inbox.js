import { api } from "../api.js";
import { alertBox, badge, confirmDialog, emptyState, field, fill, h, icon, pageHead, plural, statusBadge, toast, when, withBusy } from "../dom.js";

const MODE_INFO = {
  off: ["Off", "Messages go out exactly as you wrote them. Replies are only recorded."],
  review: ["Review", "Claude drafts each message and reply. Nothing is sent until you approve it."],
  autonomous: ["Autonomous", "Claude writes and sends messages and replies on its own, within your limits."],
};

export async function render({ state }) {
  let ai = await api.get("/api/ai");
  let selected = null;
  const root = h("div", { class: "stack" });
  const list = h("div", { class: "list", role: "list" });
  const threadBox = h("div", { class: "stack" });

  // ---------------------------------------------------------------- AI settings card
  function settingsCard() {
    let mode = ai.mode;
    const max = h("input", { type: "number", min: 0, max: 10, value: ai.max_auto_replies });
    const delay = h("input", { type: "number", min: 0, max: 120, value: ai.reply_delay_minutes });
    const disclose = h("input", { type: "checkbox", checked: ai.disclose });
    const radios = Object.keys(MODE_INFO).map((m) => h("label", { class: `mode ${m === mode ? "on" : ""}`, dataset: { mode: m } },
      h("input", { type: "radio", name: "ai-mode", value: m, checked: m === mode, class: "sr", onchange: () => { mode = m; radios.forEach((r) => r.classList.toggle("on", r.dataset.mode === m)); } }),
      h("b", {}, MODE_INFO[m][0]), h("span", { class: "hint" }, MODE_INFO[m][1])));

    async function save(btn) {
      if (mode === "autonomous" && ai.mode !== "autonomous" && !(await confirmDialog({ title: "Let Claude send messages without your approval?",
        body: `Claude will write and send invites, messages and replies to the people you chose, within your daily limits and sending hours. It hands pricing, legal, complaints and anything unclear to you, and stops for anyone who asks it to. You can switch back at any time${disclose.checked ? "." : ". Warning: you turned off the notice that an AI wrote the messages. In the EU, people should be told when they are talking to an AI."}`,
        confirmLabel: "Turn on Autonomous", danger: true }))) return;
      await withBusy(btn, "Saving…", async () => {
        try {
          await api.post("/api/ai/settings", { mode, max_auto_replies: Number(max.value), reply_delay_minutes: Number(delay.value), disclose: disclose.checked, confirm: mode === "autonomous" });
          toast(`AI mode: ${MODE_INFO[mode][0]}.`);
          ai = await api.get("/api/ai");
          paintTop();
        } catch (e) { toast(e.message, "bad"); }
      });
    }

    return h("div", { class: "card stack" },
      h("div", { class: "card-head" }, h("div", {}, h("h2", {}, "AI assistant"), h("p", { class: "muted" }, `Applies to live LinkedIn sending. Model: ${ai.model}.`)),
        ai.mode === "autonomous" ? badge("Autonomous is on", "b-warn") : ai.mode === "review" ? badge("Review mode", "b-accent") : badge("Off")),
      !ai.configured && alertBox("info", "Not set up yet. Add ANTHROPIC_API_KEY to this app's environment to turn the AI on."),
      h("div", { class: "modes", role: "radiogroup", "aria-label": "AI mode" }, radios),
      h("div", { class: "cols-3" },
        field("Automatic replies per person", max, "After this many, you take over."),
        field("Wait before replying (minutes)", delay, "So answers don't arrive instantly."),
        h("label", { class: "check", style: "align-self:end" }, disclose, h("span", {}, h("b", {}, "Say an AI assistant wrote it"), h("span", { class: "hint" }, "Adds a short line to autonomous messages. Recommended.")))),
      h("div", { class: "row spread" }, h("span", { class: "fine" }, `${ai.calls_left} of ${ai.daily_call_cap} AI requests left today${ai.waiting ? `, ${plural(ai.waiting, "item")} waiting for you` : ""}.`),
        h("button", { class: "btn btn-primary", type: "button", onclick: (e) => save(e.currentTarget) }, "Save AI settings")));
  }

  const top = h("div", {});
  const paintTop = () => fill(top, settingsCard());

  // ---------------------------------------------------------------- conversations
  const attention = { needs_you: ["Needs you", "b-bad"], draft: ["Draft waiting", "b-warn"] };

  async function loadList() {
    const { conversations } = await api.get("/api/inbox");
    fill(list, conversations.length === 0 ? h("p", { class: "muted" }, "No conversations yet. Messages you send and replies you get appear here.") :
      conversations.map((c) => h("button", { class: "list-item", type: "button", "aria-current": c.key === selected, onclick: () => open(c.key) },
        h("div", { class: "row spread" }, h("b", {}, c.name), c.attention ? badge(...attention[c.attention]) : c.replied ? badge("Replied", "b-ok") : null),
        h("div", { class: "fine trunc-line" }, c.last_text || "…"), h("div", { class: "fine" }, c.company || ""))));
    return conversations;
  }

  function bubble(m) {
    if (m.dir === "note") return h("div", { class: "note" }, m.text, " · ", when(m.at));
    const mine = m.dir === "out";
    return h("div", { class: `bubble-row ${mine ? "mine" : ""}` }, h("div", { class: `bubble ${mine ? "out" : "in"}` },
      m.subject && h("div", { class: "subject" }, m.subject), h("div", { class: "text" }, m.text),
      h("div", { class: "meta" }, when(m.at), m.kind === "ai_reply" && " · AI reply", m.kind === "step" && " · sequence step")));
  }

  function draftCard(d, refresh) {
    const area = h("textarea", { rows: 5, placeholder: d.status === "escalated" ? "Write your reply" : "" }, d.body);
    const decide = async (action, btn) => {
      await withBusy(btn, action === "approve" ? "Approving…" : "Rejecting…", async () => {
        try { await api.post("/api/ai/drafts/decide", { id: d.id, action, ...(action === "approve" ? { body: area.value } : {}) }); toast(action === "approve" ? "Approved. It sends on the next check." : "Rejected."); await refresh(); }
        catch (e) { toast(e.message, "bad"); }
      });
    };
    if (d.status === "approved") return h("div", { class: "alert alert-info" }, icon("info"), h("div", {}, h("b", {}, "Approved, sending soon. "), d.body));
    return h("div", { class: "card stack", style: "padding:16px" },
      h("div", { class: "row spread" }, h("b", {}, d.status === "escalated" ? "Needs you" : `AI draft${d.kind === "step" ? ` for step ${d.step}` : " reply"}, waiting for approval`), badge(d.channel.replace("_", " "))),
      d.reason && h("p", { class: "muted" }, d.status === "escalated" ? `Why: ${d.reason}` : d.reason), area,
      h("div", { class: "row" }, h("button", { class: "btn btn-primary", type: "button", onclick: (e) => decide("approve", e.currentTarget) }, icon("check"), d.status === "escalated" ? "Send my reply" : "Approve & send"),
        h("button", { class: "btn", type: "button", onclick: (e) => decide("reject", e.currentTarget) }, "Reject")));
  }

  async function open(key) {
    selected = key;
    const t = await api.get(`/api/inbox/${key}`);
    const refresh = async () => { await loadList(); await open(key); ai = await api.get("/api/ai"); paintTop(); };
    fill(threadBox,
      h("div", { class: "card stack" },
        h("div", { class: "row spread" }, h("div", {}, h("h2", {}, t.contact.name), h("div", { class: "muted" }, [t.contact.title, t.contact.company].filter(Boolean).join(", "))),
          h("div", { class: "row" }, statusBadge(t.contact.status), t.contact.linkedin && h("a", { class: "btn btn-sm", href: t.contact.linkedin, target: "_blank", rel: "noopener noreferrer" }, "LinkedIn profile"))),
        h("div", { class: "thread", role: "log", "aria-label": `Conversation with ${t.contact.name}` }, t.messages.length ? t.messages.map(bubble) : h("p", { class: "muted" }, "Nothing has been sent or received yet."))),
      ...t.drafts.map((d) => draftCard(d, refresh)));
    document.querySelectorAll(".list-item").forEach((el) => el.setAttribute("aria-current", String(el.querySelector("b")?.textContent === t.contact.name)));
  }

  // ---------------------------------------------------------------- assemble, and keep fresh while the page is open
  const conversations = await loadList();
  paintTop();
  if (conversations.length) { selected = conversations[0].key; await open(selected); }
  const timer = setInterval(async () => {
    if (!document.body.contains(root)) { clearInterval(timer); return; }
    try { await loadList(); if (selected && !document.querySelector("textarea:focus")) await open(selected); } catch { /* the next tick tries again */ }
  }, 15000);

  fill(root, pageHead("Inbox", "Conversations", "Every message sent and every reply, with any AI drafts waiting for your approval."), top,
    conversations.length === 0 ? emptyState("No conversations yet", "Once messages go out through live sending, they show up here with the replies.") :
      h("div", { class: "two-pane" }, list, threadBox));
  return root;
}
