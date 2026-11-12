// All text is inserted with textContent, never innerHTML, so uploaded data cannot inject markup.
const TOKEN = document.querySelector('meta[name="page-token"]').content;
const $ = (id) => document.getElementById(id);
const COLS = ["Company Name", "Website", "HQ Location", "Company Size", "Contact Person Name", "Designation/Job Title", "LinkedIn URL", "Mobile No.", "Email ID"];

function el(tag, props = {}, ...kids) {
  const node = Object.assign(document.createElement(tag), props);
  for (const k of kids.flat()) node.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return node;
}

async function api(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: { "x-page-token": TOKEN, ...(opts.headers || {}) } });
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok && res.status !== 207) throw Object.assign(new Error(data?.error || `Request failed (${res.status})`), { data });
  return data;
}

function say(node, text, kind = "") { node.textContent = text; node.className = `msg ${kind}`; }
function mark(step) {
  document.querySelectorAll("#steps li").forEach((li) => {
    const n = Number(li.dataset.step);
    li.className = n < step ? "done" : n === step ? "on" : "";
  });
}
const stat = (value, label) => el("div", { className: "stat" }, el("b", {}, value), el("small", {}, label));
const table = (cols, rows) => el("div", { className: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, cols.map((c) => el("th", {}, c)))),
  el("tbody", {}, rows.map((r) => el("tr", {}, cols.map((c) => el("td", {}, r[c] ?? "")))))));
const show = (...ids) => ids.forEach((id) => $(id).classList.remove("hidden"));

async function init() {
  const state = await api("/api/state");
  if (state.hosted) {
    $("banner").textContent = `Public demo: no login. Your files are kept in memory for ${state.ttl_minutes} minutes of inactivity, then discarded. CRM push is disabled here. Please use sample or non-personal data.`;
    $("banner").classList.remove("hidden");
  }
  $("slots").replaceChildren(...state.slots.map((s) => el("label", { className: "slot" },
    el("span", {}, `${s.key} ${s.label}`), el("small", {}, `Sheet: ${s.sheets.join(", ")}`),
    el("input", { type: "file", name: s.key, accept: ".xlsx" }))));
  if (state.has_result) await showResult();
}

async function upload(ev) {
  ev.preventDefault();
  const msg = $("upload-msg");
  say(msg, "Processing...");
  try {
    await api("/api/process", { method: "POST", body: new FormData($("upload")) });
    say(msg, "Done.", "ok");
    await showResult();
  } catch (err) {
    const problems = err.data?.problems;
    say(msg, problems ? Object.entries(problems).map(([k, v]) => `File ${k}: ${v}`).join("  |  ") : err.message, "bad");
  }
}

async function useSample() {
  try { await api("/api/sample", { method: "POST" }); say($("upload-msg"), "Sample data processed.", "ok"); await showResult(); }
  catch (err) { say($("upload-msg"), err.message, "bad"); }
}

async function showResult() {
  const { summary: s, rows, removed, truncated } = await api("/api/result");
  $("clean").replaceChildren(
    el("div", { className: "stats" }, stat(s.source_rows, "source rows read"), stat(s.removed, "invalid rows removed"), stat(s.kept, "rows kept and standardized")),
    el("p", { className: "hint" }, "Removed because: " + (Object.entries(s.removed_reasons).map(([r, n]) => `${r} (${n})`).join(", ") || "nothing")),
    removed.length ? table(["source", "ref", "name", "company", "reason"], removed) : "");
  $("merge").replaceChildren(
    el("div", { className: "stats" }, stat(s.people, "unique contacts"), stat(s.duplicates_merged, "duplicates merged"), stat(s.review_flags, "review flags"),
      stat(s.with_email, "with e-mail"), stat(s.with_mobile, "with mobile"), stat(s.with_linkedin, "with LinkedIn")),
    table(COLS, rows),
    truncated ? el("p", { className: "hint" }, "Showing the first rows only. Download the workbook for all of them.") : "",
    el("div", { className: "row" },
      el("a", { className: "btn primary", href: "/api/download/final.xlsx" }, "Download Final_Contact_List.xlsx"),
      el("a", { className: "btn", href: "/api/download/audit.xlsx" }, "Download Cleaning_Audit.xlsx")));
  show("s2", "s3", "s4");
  mark(4);
  await showCrm();
}

async function showCrm() {
  const [state, plan] = await Promise.all([api("/api/state"), api("/api/crm/plan")]);
  const msg = el("div", { className: "msg", role: "status" });
  const test = el("button", { type: "button" }, "Test HubSpot connection");
  test.disabled = !state.crm.configured;
  test.onclick = async () => {
    try { const r = await api("/api/crm/test", { method: "POST" }); say(msg, `Connected to HubSpot account ${r.portal_id}.`, "ok"); }
    catch (err) { say(msg, err.message, "bad"); }
  };
  const confirm = el("input", { type: "number", min: "0", placeholder: String(plan.contacts), ariaLabel: "Type the number of contacts to confirm" });
  const push = el("button", { type: "button", className: "primary" }, "Push to HubSpot");
  push.disabled = !state.crm.push_enabled;
  push.onclick = async () => {
    say(msg, "Pushing...");
    try {
      const r = await api("/api/crm/push", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ confirm_contacts: Number(confirm.value) }) });
      say(msg, `${r.ok ? "Done" : "Stopped early"}: ${r.contacts} contacts, ${r.companies} companies, ${r.associations} associations.${r.errors.length ? " " + r.errors.join(" ") : ""}`, r.ok ? "ok" : "bad");
    } catch (err) { say(msg, err.message, "bad"); }
  };
  const note = !state.crm.configured ? "No HubSpot token loaded: this is a preview only."
    : !state.crm.push_enabled ? "Token loaded, but pushing is off: this is a preview only." : "Pushing is ON. Check the preview, then type the contact count to confirm.";
  $("crm").replaceChildren(
    el("p", { className: "hint" }, note),
    el("div", { className: "stats" }, stat(plan.contacts, "contacts to upsert (by e-mail)"), stat(plan.companies, "companies to upsert (by domain)"),
      stat(plan.associations, "contact-company links"), stat(plan.skipped.length, "rows skipped")),
    el("p", { className: "hint" }, "Blank fields are never sent, so existing CRM values are not erased. A custom company property (" + plan.custom_properties.join(", ") + ") is created if missing."),
    plan.skipped.length ? table(["name", "company", "reason"], plan.skipped) : "",
    el("h3", {}, "Preview of contacts"), table(["email", "firstname", "lastname", "jobtitle", "mobilephone", "company"], plan.sample_contacts),
    el("div", { className: "row" }, test, confirm, push), msg);
}

$("upload").addEventListener("submit", upload);
$("sample").addEventListener("click", useSample);
init().catch((err) => say($("upload-msg"), err.message, "bad"));
