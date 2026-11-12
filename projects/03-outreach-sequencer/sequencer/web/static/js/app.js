import { api, ApiError } from "./api.js";
import { alertBox, clear, confirmDialog, h, icon, skeleton, toast } from "./dom.js";
import * as importPage from "./pages/import.js";
import * as validatePage from "./pages/validate.js";
import * as sequencePage from "./pages/sequence.js";
import * as messagesPage from "./pages/messages.js";
import * as rulesPage from "./pages/rules.js";
import * as launchPage from "./pages/launch.js";
import * as reportPage from "./pages/report.js";
import * as inboxPage from "./pages/inbox.js";

const STEPS = [
  { id: "import", label: "Import contacts", page: importPage }, { id: "validate", label: "Validate", page: validatePage },
  { id: "sequence", label: "Build sequence", page: sequencePage }, { id: "messages", label: "Write messages", page: messagesPage },
  { id: "rules", label: "Sending rules", page: rulesPage }, { id: "launch", label: "Launch & track", page: launchPage },
  { id: "report", label: "Report", page: reportPage },
  { id: "inbox", label: "Inbox", page: inboxPage },
];
const main = document.getElementById("main");
let renderToken = 0;

const route = () => (location.hash.replace(/^#\//, "") || "").split("?")[0];
export const go = (id) => { if (route() === id) render(); else location.hash = `#/${id}`; };

function sidebar(state, current) {
  const nav = clear(document.getElementById("steps"));
  STEPS.forEach((s, i) => {
    const done = !!state.done[s.id];
    nav.append(h("a", { class: "step", href: `#/${s.id}`, "aria-current": s.id === current ? "page" : null, dataset: { done } },
      h("span", { class: "step-dot" }, done ? icon("check") : i + 1), h("span", {}, s.label), done && h("span", { class: "sr" }, "(done)")));
  });
}

export async function render() {
  const token = ++renderToken;
  let state;
  try { state = await api.get("/api/state"); } catch (err) { clear(main).append(alertBox("bad", err.message)); return; }
  if (token !== renderToken) return;
  const current = STEPS.find((s) => s.id === route())?.id ?? (state.done.import ? STEPS.find((s) => !state.done[s.id])?.id ?? "report" : "import");
  sidebar(state, current);
  const note = document.querySelector(".side-foot .fine");
  if (note) note.textContent = state.live_sending ? "Live sending is ON. Real messages go out from your account." : "Sending is simulated unless you start live sending.";
  clear(main).append(skeleton(4));
  const step = STEPS.find((s) => s.id === current);
  document.title = `${step.label} · Outreach Sequencer`;
  try {
    const node = await step.page.render({ state, go, refresh: render });
    if (token !== renderToken) return;
    clear(main).append(node);
    main.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  } catch (err) {
    if (token !== renderToken) return;
    clear(main).append(alertBox("bad", err instanceof ApiError ? err.message : "Something went wrong showing this page. Reload to try again."));
    console.error(err);
  }
}

async function loadSample() {
  const state = await api.get("/api/state");
  if (state.total && !(await confirmDialog({ title: "Replace your project with the sample?", body: "Your current list, messages and results will be replaced.", confirmLabel: "Load sample", danger: true }))) return;
  await api.post("/api/sample");
  toast("Sample project loaded: 36 contacts, 5 templates and one sequence.");
  location.hash = "#/validate";
  render();
}

async function startOver() {
  if (!(await confirmDialog({ title: "Start over?", body: "This deletes the imported list, messages, rules and results in this app. Your original files are not touched.", confirmLabel: "Delete and start over", danger: true }))) return;
  await api.post("/api/reset", { scope: "all" });
  toast("Cleared. Ready for a new list.");
  location.hash = "#/import";
  render();
}

const guarded = (fn) => () => fn().catch((e) => toast(e.message, "bad"));
document.getElementById("menu-sample").addEventListener("click", guarded(loadSample));
document.getElementById("menu-reset").addEventListener("click", guarded(startOver));
window.addEventListener("hashchange", render);
render();
