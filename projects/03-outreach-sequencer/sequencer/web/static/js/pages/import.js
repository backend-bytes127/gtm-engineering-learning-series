import { api } from "../api.js";
import { addContactCard } from "./add-contact.js";
import { fill, alertBox, badge, emptyState, field, h, icon, pageHead, toast, withBusy } from "../dom.js";

const LABELS = { name: "Full name", first_name: "First name", last_name: "Last name", company: "Company", title: "Job title", email: "Email",
  linkedin_url: "LinkedIn URL", sequence: "Sequence", status: "Status (for opt-outs)" };
const REQUIRED_HINT = "Needs a name (full, or first and last) and at least an email or LinkedIn URL.";

export async function render({ state, go, refresh }) {
  const wrap = h("div", { class: "stack" });
  const intro = pageHead("Step 1", "Import your contact list", "Upload a clean list as CSV or Excel. The columns are matched to the tool's fields automatically, and you can change any match before anything is checked.");
  wrap.append(intro);
  if (state.import_source) {
    wrap.append(alertBox("info", `Current list: ${state.import_source}, ${state.total + state.removed} rows. Importing another file replaces it and clears any results.`));
  }
  const area = h("div", {});
  wrap.append(area);
  showDrop(area, { go, refresh });
  wrap.append(addContactCard(state, refresh));
  return wrap;
}

function showDrop(area, ctx) {
  const input = h("input", { type: "file", accept: ".csv,.xlsx", class: "sr", id: "file", onchange: () => input.files[0] && handle(input.files[0]) });
  const zone = h("div", { class: "dropzone", ondragover: (e) => { e.preventDefault(); zone.classList.add("over"); }, ondragleave: () => zone.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); zone.classList.remove("over"); e.dataTransfer.files[0] && handle(e.dataTransfer.files[0]); } },
    icon("upload"), h("h2", {}, "Drop a CSV or XLSX file here"), h("p", { class: "muted" }, "Up to 10 MB. Project 02's Final_Contact_List.xlsx works as is."),
    h("label", { class: "btn btn-primary", for: "file" }, "Choose a file"), input,
    h("p", { class: "fine" }, "No list handy? Use “Load sample project” at the bottom left."));
  fill(area, zone);

  async function handle(file) {
    zone.replaceChildren(h("p", {}, `Reading ${file.name}…`));
    try { showMapping(area, await api.upload(file), ctx); }
    catch (err) { toast(err.message, "bad"); showDrop(area, ctx); }
  }
}

function showMapping(area, up, ctx) {
  const selects = {};
  const suppression = h("textarea", { rows: 4, placeholder: "ada@example.com\n@blocked-company.com\nhttps://www.linkedin.com/in/someone", "aria-label": "Do-not-contact list" });
  const seqName = h("input", { type: "text", value: "Outbound Intro", "aria-label": "Default sequence" });
  const problem = h("div", { "aria-live": "polite" });

  const rows = Object.entries(LABELS).map(([f, label]) => {
    const sel = h("select", { "aria-label": `Column for ${label}`, onchange: () => { renderSample(f); check(); } },
      h("option", { value: "" }, "Not mapped"), ...up.headers.map((hd) => h("option", { value: hd, selected: up.suggested[f] === hd }, hd)));
    selects[f] = sel;
    const sample = h("td", { class: "trunc muted" });
    const renderSample = (key) => { const i = up.headers.indexOf(selects[key].value); sample.textContent = i < 0 ? "" : up.rows.map((r) => r[i]).filter(Boolean).slice(0, 2).join("  ·  "); };
    renderSample(f);
    return h("tr", {}, h("td", {}, h("b", {}, label)), h("td", {}, sel), sample);
  });

  const go = h("button", { class: "btn btn-primary", type: "button", onclick: () => run(go) }, "Check contacts", icon("arrow"));
  function check() {
    const v = (f) => selects[f].value;
    const hasName = v("name") || v("first_name") || v("last_name");
    const ok = hasName && (v("email") || v("linkedin_url"));
    go.disabled = !ok;
    problem.replaceChildren(ok ? "" : alertBox("warn", REQUIRED_HINT));
  }
  async function run(button) {
    const mapping = Object.fromEntries(Object.entries(selects).map(([f, s]) => [f, s.value]).filter(([, v]) => v));
    await withBusy(button, "Checking…", async () => {
      try {
        const res = await api.post("/api/import", { upload_id: up.upload_id, filename: up.filename, mapping, default_sequence: seqName.value, suppression_text: suppression.value });
        toast(`${res.kept} of ${res.read} contacts are valid. ${res.removed} removed.`);
        ctx.go("validate");
      } catch (err) { toast(err.message, "bad"); }
    });
  }

  fill(area, h("div", { class: "stack" },
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("div", {}, h("h2", {}, "Match your columns"), h("p", { class: "muted" }, `${up.filename}: ${up.total} rows, ${up.headers.length} columns`)),
        h("button", { class: "btn btn-sm", type: "button", onclick: () => showDrop(area, ctx) }, "Choose a different file")),
      h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Tool field"), h("th", {}, "Your column"), h("th", {}, "Example values"))), h("tbody", {}, rows))),
      h("div", { style: "margin-top:16px" }, problem)),
    h("div", { class: "card cols-2" },
      field("Sequence for rows that have none", seqName, "Contacts are assigned to this sequence. You build it in step 3."),
      field("Do-not-contact list (optional)", suppression, "One per line: an email, an @domain or a LinkedIn profile URL. Matches are removed.")),
    h("div", { class: "row spread" }, h("p", { class: "fine" }, "Nothing is sent in this step. Records are only checked."), go)));
  check();
}
