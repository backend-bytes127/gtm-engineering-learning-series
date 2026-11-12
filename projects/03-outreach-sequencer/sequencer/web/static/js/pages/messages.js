import { api } from "../api.js";
import { fill, CHANNEL, alertBox, badge, confirmDialog, debounce, emptyState, field, h, icon, pageHead, toast, withBusy } from "../dom.js";

export async function render({ state, go, refresh }) {
  let cfg = await api.get("/api/config");
  const contacts = state.total ? (await api.get("/api/contacts")).contacts : [];
  let current = cfg.templates[0]?.id ?? null;
  let draft = null, dirty = false, isNew = false, issues = [], previewContact = contacts[0]?.key ?? "";
  const root = h("div", { class: "stack" });
  const used = () => new Set(cfg.sequences.flatMap((s) => s.steps.map((x) => x.template)));
  const liveUsed = () => new Set(cfg.sequences.filter((s) => s.live).flatMap((s) => s.steps.map((x) => x.template)));
  const reload = async () => { cfg = await api.get("/api/config"); };
  const savedCopy = () => cfg.templates.find((x) => x.id === draft?.id);

  function pick(id) {
    current = id; isNew = false;
    const t = cfg.templates.find((x) => x.id === id);
    draft = t ? { id: t.id, channel: t.channel, subject: t.subject, body: t.body } : null;
    dirty = false; issues = t?.issues ?? [];
    paint(); runChecks();
  }

  const runChecks = debounce(async () => {
    if (!draft) return;
    try {
      const [lint, prev] = await Promise.all([api.post("/api/lint", draft), api.post("/api/preview", { ...draft, contact: previewContact })]);
      issues = lint.issues;
      paintFeedback(prev);
    } catch (e) { toast(e.message, "bad"); }
  }, 250);

  const touch = () => { dirty = true; runChecks(); paintSaveState(); };

  function insertVar(name) {
    const area = root.querySelector("#body");
    const { selectionStart: a, selectionEnd: b } = area;
    draft = { ...draft, body: `${area.value.slice(0, a)}{{${name}}}${area.value.slice(b)}` };
    area.value = draft.body;
    area.focus();
    area.setSelectionRange(a + name.length + 4, a + name.length + 4);
    touch();
  }

  function paintSaveState() {
    const errs = issues.filter((i) => i.severity === "error");
    const save = root.querySelector("#save");
    if (save) save.disabled = !dirty || !draft.id;
    const approve = root.querySelector("#approve");
    if (!approve) return;
    const saved = savedCopy();
    approve.disabled = dirty || errs.length > 0 || !saved || saved.approved;
    approve.title = dirty ? "Save your changes first" : errs.length ? "Fix the errors first" : saved?.approved ? "Already approved" : "";
  }

  const bullets = (items) => h("ul", { style: "margin:6px 0 0;padding-left:18px" }, items.map((i) => h("li", {}, i.message)));

  function paintFeedback(prev) {
    const box = root.querySelector("#feedback");
    if (!box) return;
    const errs = issues.filter((i) => i.severity === "error");
    const warns = issues.filter((i) => i.severity === "warning");
    const forContact = prev.issues ?? [];
    fill(box, 
      contacts.length > 0 && field("Preview with", h("select", { onchange: (e) => { previewContact = e.target.value; runChecks(); } },
        contacts.slice(0, 80).map((c) => h("option", { value: c.key, selected: c.key === previewContact }, `${c.name}${c.company ? ` · ${c.company}` : " · no company"}`)))),
      h("div", { class: "preview", "aria-label": "Preview" },
        h("div", { class: "row spread" }, h("span", { class: "eyebrow", style: "margin:0" }, `Preview for ${prev.contact.name}`),
          draft.channel === "linkedin_invite" && badge(`${prev.chars} / ${cfg.limits.invite_chars}`, prev.chars > cfg.limits.invite_chars ? "b-bad" : "")),
        draft.channel === "email" && h("div", { class: "subject" }, prev.subject || h("span", { class: "miss" }, "No subject")),
        h("div", { class: "body" }, prev.body)),
      prev.fallbacks.length > 0 && alertBox("info", `Using the fallback text for: ${prev.fallbacks.join(", ")}.`),
      forContact.length > 0 && alertBox("bad", h("b", {}, "This contact's message can't be sent: "), forContact.map((i) => i.message).join("; ")),
      errs.length > 0 && alertBox("bad", h("b", {}, "Fix before approving"), bullets(errs)),
      warns.length > 0 && alertBox("warn", h("b", {}, "Worth a look"), bullets(warns)),
      errs.length + warns.length + forContact.length === 0 && alertBox("ok", "All checks pass."));
    paintSaveState();
  }

  async function save(btn) {
    await withBusy(btn, "Saving…", async () => {
      try { await api.post("/api/templates", draft); await reload(); current = draft.id; toast("Saved. Approve it before launch."); await refresh(); }
      catch (e) { toast(e.message, "bad"); }
    });
  }
  async function approve(btn, ids) {
    await withBusy(btn, "Approving…", async () => {
      try { const r = await api.post("/api/templates/approve", { ids }); toast(`Approved ${r.approved.length}.`); await refresh(); }
      catch (e) { toast(e.message, "bad"); }
    });
  }
  async function remove() {
    if (!(await confirmDialog({ title: `Delete “${draft.id}”?`, body: "This can't be undone.", confirmLabel: "Delete", danger: true }))) return;
    try { await api.post("/api/templates/delete", { id: draft.id }); toast("Deleted."); await refresh(); } catch (e) { toast(e.message, "bad"); }
  }
  function add() {
    const id = `message_${cfg.templates.length + 1}`;
    draft = { id, channel: "email", subject: "", body: "Hi {{first_name}},\n\n\n\n{{sender_name}}\n\n{{unsubscribe_line}}" };
    current = id; isNew = true; dirty = true; issues = [];
    paint(); runChecks();
    root.querySelector("#tid")?.focus();
  }
  async function choose(id) {
    if (dirty && !(await confirmDialog({ title: "Discard unsaved changes?", body: "Your edits to this message haven't been saved.", confirmLabel: "Discard" }))) return;
    pick(id);
  }

  const list = () => {
    const u = used();
    return h("div", { class: "list", role: "list" }, cfg.templates.map((t) => h("button", { class: "list-item", type: "button", "aria-current": t.id === current, onclick: () => choose(t.id) },
      h("div", { class: "row spread" }, h("b", { class: "mono" }, t.id), t.approved ? badge("Approved", "b-ok") : badge("Needs approval", "b-warn")),
      h("div", { class: "row fine" }, icon(CHANNEL[t.channel]?.icon ?? "info"), CHANNEL[t.channel]?.label ?? t.channel, !u.has(t.id) && " · not in a sequence"))));
  };

  function editor() {
    const locked = liveUsed().has(draft.id);
    const rows = draft.channel === "email" ? 8 : 5;
    return h("div", { class: "stack" },
      locked && alertBox("info", "This message is used by a live sequence and can't be edited now."),
      h("div", { class: "card stack" },
        h("div", { class: "cols-2" },
          field("Message id", h("input", { type: "text", id: "tid", value: draft.id, maxLength: 60, disabled: !isNew, onchange: (e) => { draft = { ...draft, id: e.target.value.trim() }; touch(); } }), "Letters, numbers, _ and - only."),
          field("Channel", h("select", { disabled: locked, onchange: (e) => { draft = { ...draft, channel: e.target.value }; dirty = true; paint(); runChecks(); } },
            cfg.channels.map((c) => h("option", { value: c, selected: c === draft.channel }, CHANNEL[c].label))))),
        draft.channel === "email" && field("Subject", h("input", { type: "text", value: draft.subject, disabled: locked, oninput: (e) => { draft = { ...draft, subject: e.target.value }; touch(); } })),
        field("Message", h("textarea", { id: "body", rows, disabled: locked, oninput: (e) => { draft = { ...draft, body: e.target.value }; touch(); } }, draft.body),
          draft.channel === "linkedin_invite" ? `LinkedIn invites are limited to ${cfg.limits.invite_chars} characters.` : "Use {{first_name}} style variables. Add a fallback with {{company|your team}}."),
        h("div", {}, h("div", { class: "label", style: "margin-bottom:8px" }, "Insert a variable"),
          h("div", { class: "chips" }, cfg.variables.all.map((v) => h("button", { class: "chip", type: "button", disabled: locked, onclick: () => insertVar(v) }, `{{${v}}}`)))),
        h("div", { id: "feedback", class: "stack" }),
        h("div", { class: "row spread actionbar" },
          h("button", { class: "btn btn-danger btn-sm", type: "button", disabled: locked || isNew || used().has(draft.id), onclick: remove, title: used().has(draft.id) ? "Remove it from the sequence first" : "" }, icon("trash"), "Delete"),
          h("div", { class: "row" }, h("button", { class: "btn", id: "save", type: "button", disabled: true, onclick: (e) => save(e.currentTarget) }, "Save"),
            h("button", { class: "btn btn-primary", id: "approve", type: "button", disabled: true, onclick: (e) => approve(e.currentTarget, [draft.id]) }, icon("check"), "Approve")))),
      null);
  }

  function paint() {
    const pending = cfg.templates.filter((t) => !t.approved).length;
    fill(root, 
      pageHead("Step 4", "Write your messages", "Every message is checked as you type and shown filled in with a real contact. Only approved messages can be sent, and editing an approved message un-approves it.",
        pending > 0 ? h("button", { class: "btn", type: "button", onclick: (e) => approve(e.currentTarget, null) }, icon("check"), `Approve all (${pending})`) : badge("All approved", "b-ok"),
        h("button", { class: "btn btn-primary", type: "button", onclick: () => go("rules") }, "Next: sending rules", icon("arrow"))),
      cfg.templates.length === 0 && !draft
        ? emptyState("No messages yet", "Write the email, invite and DM that your sequence steps will use.", h("button", { class: "btn btn-primary", type: "button", onclick: add }, icon("plus"), "New message"))
        : h("div", { class: "two-pane" }, h("div", { class: "stack" }, list(), h("button", { class: "btn btn-block", type: "button", onclick: add }, icon("plus"), "New message")), draft ? editor() : ""));
    paintSaveState();
  }

  if (current) pick(current); else paint();
  return root;
}
