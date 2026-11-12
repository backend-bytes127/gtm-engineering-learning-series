// DOM helpers. Contact data is untrusted, so text is only ever set through textContent / createTextNode, never innerHTML.
const SVG_NS = "http://www.w3.org/2000/svg";

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    // ARIA state attributes are strings ("true"/"false"); a boolean would otherwise become an empty attribute.
    if (key.startsWith("aria-") && typeof value === "boolean") { el.setAttribute(key, String(value)); continue; }
    if (value === false || value == null) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on")) el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key in el && key !== "list" && key !== "form") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el) { el.replaceChildren(); return el; }

// Like replaceChildren, but skips false/null so `cond && element` never prints the word "false".
export function fill(el, ...children) {
  el.replaceChildren(...children.flat(Infinity).filter((c) => c != null && c !== false));
  return el;
}

const ICONS = {
  mail: "M3 6h18v12H3zM3 7l9 6 9-6", linkedin: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M19 8v6M22 11h-6",
  message: "M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-5.4A8 8 0 1 1 21 12", check: "M5 12.5l4.5 4.5L19 7.5", x: "M6 6l12 12M18 6L6 18",
  alert: "M12 8v5M12 17h.01M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0",
  info: "M12 11v5M12 8h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18", upload: "M12 16V4M7 9l5-5 5 5M4 20h16", arrow: "M5 12h14M13 6l6 6-6 6",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13", plus: "M12 5v14M5 12h14", up: "M6 15l6-6 6 6", down: "M6 9l6 6 6-6", play: "M7 4l13 8-13 8z",
  download: "M12 4v12M7 11l5 5 5-5M4 20h16", search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14M20 20l-4-4", reset: "M4 4v6h6M4.5 15a8 8 0 1 0 2-8.5L4 10",
  lock: "M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z", file: "M6 3h8l4 4v14H6zM14 3v4h4",
};

export function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICONS[name] || ICONS.info);
  svg.append(path);
  return svg;
}

export const CHANNEL = {
  email: { label: "Email", icon: "mail" }, linkedin_invite: { label: "LinkedIn invite", icon: "linkedin" },
  linkedin_message: { label: "LinkedIn message", icon: "message" },
};

const STATUS_TONE = { "Not Started": "", "In Sequence": "b-accent", Replied: "b-ok", "Meeting Booked": "b-ok", Completed: "", Stopped: "b-bad" };
export function statusBadge(status) { return h("span", { class: `badge ${STATUS_TONE[status] ?? ""}` }, status); }
export function badge(text, tone = "") { return h("span", { class: `badge ${tone}` }, text); }

const STOP_LABEL = { bounced: "Bounced", opted_out: "Unsubscribed", draft_incomplete: "Held back: missing data", send_failed: "Send failed" };
export function stopLabel(reason) { return STOP_LABEL[reason] || reason; }

export function alertBox(tone, ...children) {
  const name = { info: "info", warn: "alert", bad: "alert", ok: "check" }[tone];
  return h("div", { class: `alert alert-${tone}`, role: tone === "bad" ? "alert" : null }, icon(name), h("div", {}, ...children));
}

// ---- toasts
export function toast(message, tone = "") {
  const el = h("div", { class: `toast ${tone}` }, message);
  document.getElementById("toasts").prepend(el);
  setTimeout(() => el.remove(), tone === "bad" ? 8000 : 4500);
}

// ---- overlays: focus is trapped inside, Escape closes, focus returns to what opened it
function trapFocus(root, onClose) {
  const opener = document.activeElement;
  const focusable = () => [...root.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")].filter((e) => !e.disabled);
  const onKey = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); }
    if (e.key !== "Tab") return;
    const items = focusable();
    if (!items.length) return;
    const [first, last] = [items[0], items[items.length - 1]];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  function close() { document.removeEventListener("keydown", onKey, true); root.remove(); opener?.focus?.(); onClose?.(); }
  document.addEventListener("keydown", onKey, true);
  queueMicrotask(() => (root.querySelector("[autofocus]") || focusable()[0])?.focus());
  return close;
}

export function confirmDialog({ title, body, confirmLabel, danger = false }) {
  return new Promise((resolve) => {
    let close;
    // Resolve first: close() runs onClose, which resolves false, and only the first resolution counts.
    const done = (value) => { resolve(value); close(); };
    const scrim = h("div", { class: "scrim", onclick: (e) => e.target === scrim && done(false) },
      h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "dlg-title" },
        h("h2", { id: "dlg-title" }, title), h("p", { class: "muted" }, body),
        h("div", { class: "row" },
          h("button", { class: "btn", type: "button", onclick: () => done(false) }, "Cancel"),
          h("button", { class: `btn btn-primary ${danger ? "btn-danger" : ""}`, type: "button", autofocus: true, onclick: () => done(true) }, confirmLabel))));
    document.getElementById("overlay").append(scrim);
    close = trapFocus(scrim, () => resolve(false));
  });
}

export function openDrawer(title, subtitle, content) {
  let close;
  const drawer = h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "drawer-head" }, h("div", {}, h("h2", {}, title), subtitle && h("p", { class: "muted" }, subtitle)),
      h("button", { class: "btn btn-sm", type: "button", "aria-label": "Close", onclick: () => close() }, icon("x"))),
    h("div", { class: "drawer-body" }, content));
  const scrim = h("div", { class: "scrim", style: "place-items:stretch", onclick: (e) => e.target === scrim && close() }, drawer);
  document.getElementById("overlay").append(scrim);
  close = trapFocus(scrim);
  return { close, body: drawer.querySelector(".drawer-body") };
}

// ---- formatting
export const pct = (n) => (n == null ? "–" : `${Math.round(n * 100)}%`);
export const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
export function when(iso) {
  return iso ? new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
}
export function skeleton(lines = 3) { return h("div", { class: "stack", "aria-busy": "true" }, Array.from({ length: lines }, () => h("div", { class: "skel", style: "height:20px" }))); }
export function emptyState(title, text, ...actions) { return h("div", { class: "card empty" }, h("h2", {}, title), h("p", {}, text), h("div", { class: "row" }, ...actions)); }
export function pageHead(eyebrow, title, text, ...actions) {
  return h("header", { class: "page-head" }, h("div", {}, h("div", { class: "eyebrow" }, eyebrow), h("h1", {}, title), text && h("p", {}, text)), h("div", { class: "row" }, ...actions));
}
export function field(label, input, hint, error) {
  return h("label", { class: "field" }, h("span", {}, label), input, hint && h("span", { class: "hint" }, hint), error && h("span", { class: "err" }, error));
}
export function debounce(fn, ms = 250) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
export async function withBusy(button, label, task) {
  const old = button.textContent;
  button.disabled = true; button.textContent = label;
  try { return await task(); } finally { button.disabled = false; button.textContent = old; }
}
