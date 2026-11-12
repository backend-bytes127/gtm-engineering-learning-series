import { api } from "../api.js";
import { fill, CHANNEL, alertBox, badge, confirmDialog, debounce, emptyState, field, h, icon, pageHead, toast, withBusy } from "../dom.js";

export async function render({ state, go, refresh }) {
  const cfg = await api.get("/api/config");
  let sequences = structuredClone(cfg.sequences);
  let current = sequences[0]?.name ?? null;
  let draft = null, dirty = false, errors = [];
  const root = h("div", { class: "stack" });

  const select = (name) => { current = name; draft = structuredClone(sequences.find((s) => s.name === name)); dirty = false; errors = draft?.errors ?? []; paint(); };
  const newSequence = () => {
    const unused = (state.pending_sequences ?? []).find((n) => !sequences.some((s) => s.name === n));
    const name = unused ?? `Sequence ${sequences.length + 1}`;
    sequences = [...sequences, { name, live: false, steps: [], errors: [], contacts: 0 }];
    select(name); dirty = true; paint(); check();
  };
  const check = debounce(async () => {
    try { errors = (await api.post("/api/sequence/check", payload())).errors; } catch (e) { errors = [e.message]; }
    paintStatus();
  }, 200);
  const payload = () => ({ name: draft.name, steps: draft.steps });
  const edit = (fn) => { draft = fn(structuredClone(draft)); dirty = true; paint(); check(); };

  function stepCard(step, i) {
    const options = cfg.templates.filter((t) => t.channel === step.channel);
    const day = draft.steps.slice(0, i + 1).reduce((n, s) => n + s.wait_days, 0);
    const locked = draft.live;
    return h("div", { class: "t-item" },
      h("div", { class: "t-dot" }, icon(CHANNEL[step.channel]?.icon ?? "info")),
      h("div", { class: "step-card" },
        h("div", { class: "row spread" }, h("div", { class: "row" }, h("b", {}, `Step ${i + 1}`), h("span", { class: "day-tag" }, `Day ${day}`)),
          !locked && h("div", { class: "row" },
            h("button", { class: "btn btn-sm", type: "button", "aria-label": `Move step ${i + 1} up`, disabled: i === 0, onclick: () => edit((d) => { [d.steps[i - 1], d.steps[i]] = [d.steps[i], d.steps[i - 1]]; return d; }) }, icon("up")),
            h("button", { class: "btn btn-sm", type: "button", "aria-label": `Move step ${i + 1} down`, disabled: i === draft.steps.length - 1, onclick: () => edit((d) => { [d.steps[i + 1], d.steps[i]] = [d.steps[i], d.steps[i + 1]]; return d; }) }, icon("down")),
            h("button", { class: "btn btn-sm btn-danger", type: "button", "aria-label": `Delete step ${i + 1}`, onclick: () => edit((d) => { d.steps.splice(i, 1); return d; }) }, icon("trash")))),
        h("div", { class: "step-grid" },
          field("Channel", h("select", { disabled: locked, onchange: (e) => edit((d) => { d.steps[i].channel = e.target.value; d.steps[i].template = cfg.templates.find((t) => t.channel === e.target.value)?.id ?? ""; return d; }) },
            cfg.channels.map((c) => h("option", { value: c, selected: c === step.channel }, CHANNEL[c].label)))),
          field(i === 0 ? "Wait (days)" : "Wait after previous", h("input", { type: "number", min: 0, max: cfg.limits.max_wait, value: step.wait_days, disabled: locked, onchange: (e) => edit((d) => { d.steps[i].wait_days = Math.trunc(Number(e.target.value) || 0); return d; }) })),
          field("Message", h("select", { disabled: locked, onchange: (e) => edit((d) => { d.steps[i].template = e.target.value; return d; }) },
            !options.some((t) => t.id === step.template) && h("option", { value: step.template, selected: true }, step.template || "Choose a message"),
            options.map((t) => h("option", { value: t.id, selected: t.id === step.template }, t.id)))))));
  }

  function paintStatus() {
    const box = root.querySelector("#seq-status");
    if (!box) return;
    box.replaceChildren(errors.length ? alertBox("warn", h("b", {}, "Fix before saving"), h("ul", { style: "margin:6px 0 0;padding-left:18px" }, errors.map((e) => h("li", {}, e))))
      : draft?.steps.length ? alertBox("ok", "This sequence is valid.") : "");
    const save = root.querySelector("#seq-save");
    if (save) { save.disabled = !dirty || errors.length > 0 || draft.live; save.title = errors.length ? "Fix the problems above first" : !dirty ? "No changes to save" : ""; }
  }

  async function save(button) {
    await withBusy(button, "Saving…", async () => {
      try { const saved = await api.post("/api/sequence", payload()); sequences = sequences.map((s) => (s.name === saved.name ? saved : s)); if (!sequences.some((s) => s.name === saved.name)) sequences.push(saved); select(saved.name); toast("Sequence saved."); await refresh(); }
      catch (e) { errors = e.data?.errors ?? [e.message]; paintStatus(); toast(e.message, "bad"); }
    });
  }

  function paint() {
    if (!draft) { fill(root, pageHead("Step 3", "Build your sequence"), emptyState("No sequence yet", "A sequence is a list of steps. Each step has a channel, a wait, and a message.", h("button", { class: "btn btn-primary", type: "button", onclick: newSequence }, icon("plus"), "Create a sequence"))); return; }
    const totalDays = draft.steps.reduce((n, s) => n + s.wait_days, 0);
    fill(root, 
      pageHead("Step 3", "Build your sequence", "Choose the channel and wait for each step. Waits count from the previous step. A LinkedIn message can only follow an invite, and it waits until that invite is accepted.",
        h("button", { class: "btn btn-primary", id: "seq-save", type: "button", onclick: (e) => save(e.currentTarget) }, "Save sequence")),
      h("div", { class: "row" }, h("div", { class: "tabs", role: "tablist", style: "margin:0;flex:1" }, sequences.map((s) => h("button", { class: "tab", role: "tab", "aria-selected": s.name === current, onclick: () => select(s.name) }, s.name, s.live && h("span", { class: "count" }, "live")))),
        h("button", { class: "btn btn-sm", type: "button", onclick: newSequence }, icon("plus"), "New sequence")),
      draft.live && alertBox("info", "This sequence is live, so it can't be edited. Reset the results on the Launch page to change it."),
      h("div", { class: "card" },
        h("div", { class: "cols-2" }, field("Sequence name", h("input", { type: "text", value: draft.name, maxLength: 120, disabled: draft.live, onchange: (e) => { const old = draft.name; edit((d) => { d.name = e.target.value.trim() || old; return d; }); } }), "Contacts are matched to a sequence by this name."),
          h("div", { class: "field" }, h("span", {}, "At a glance"), h("div", { class: "row" }, badge(`${draft.steps.length} steps`), badge(`${totalDays} days end to end`), badge(`${draft.contacts} contacts`)))),
        h("div", { style: "margin-top:24px" }, draft.steps.length ? h("div", { class: "timeline" }, draft.steps.map(stepCard)) : emptyState("No steps yet", "Add the first step, usually an email.")),
        !draft.live && h("div", { class: "row", style: "margin-top:8px" }, h("button", { class: "btn", type: "button", disabled: draft.steps.length >= cfg.limits.max_steps, onclick: () => edit((d) => { const t = cfg.templates.find((x) => x.channel === "email") ?? cfg.templates[0]; d.steps.push({ channel: t?.channel ?? "email", wait_days: d.steps.length ? 2 : 0, template: t?.id ?? "" }); return d; }) }, icon("plus"), "Add step"),
          draft.steps.length >= cfg.limits.max_steps && h("span", { class: "fine" }, `Limit is ${cfg.limits.max_steps} steps.`))),
      h("div", { id: "seq-status", "aria-live": "polite" }),
      draft.steps.length > 0 && h("div", { class: "row spread" }, h("span", {}), h("button", { class: "btn", type: "button", onclick: () => go("messages") }, "Next: write messages", icon("arrow"))));
    paintStatus();
  }

  if (current) select(current); else paint();
  return root;
}
