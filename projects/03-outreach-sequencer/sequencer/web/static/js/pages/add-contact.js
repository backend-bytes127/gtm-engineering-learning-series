import { api } from "../api.js";
import { alertBox, field, fill, h, icon, toast, withBusy } from "../dom.js";

// A small form for adding one person by hand, checked by the same rules as a file import.
export function addContactCard(state, refresh) {
  const sequences = state.sequences.length ? state.sequences : ["Outbound Intro"];
  const inputs = {
    name: h("input", { type: "text", autocomplete: "off", maxLength: 200, required: true }),
    linkedin_url: h("input", { type: "text", placeholder: "https://www.linkedin.com/in/…", maxLength: 200 }),
    email: h("input", { type: "text", inputMode: "email", maxLength: 200 }),
    company: h("input", { type: "text", maxLength: 200 }),
    title: h("input", { type: "text", maxLength: 200 }),
    sequence: h("select", {}, sequences.map((s) => h("option", { value: s }, s))),
  };
  const message = h("div", { "aria-live": "polite" });
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, icon("plus"), "Add contact");

  async function save(event) {
    event.preventDefault();
    fill(message);
    if (!inputs.name.value.trim()) { fill(message, alertBox("warn", "Enter a name.")); inputs.name.focus(); return; }
    if (!inputs.email.value.trim() && !inputs.linkedin_url.value.trim()) { fill(message, alertBox("warn", "Add an email address or a LinkedIn URL.")); return; }
    await withBusy(submit, "Checking…", async () => {
      try {
        const body = Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value]));
        const added = await api.post("/api/contacts/add", body);
        toast(`${added.name} added.${added.flags.length ? " Added with a note, see Validate." : ""}`);
        await refresh();
      } catch (e) {
        fill(message, alertBox("bad", e.message));
      }
    });
  }

  return h("form", { class: "card form-narrow", novalidate: true, onsubmit: save },
    h("div", {}, h("h2", {}, "Or add one contact by hand"), h("p", { class: "muted" }, "Checked exactly like a file import: a valid email or LinkedIn profile, no duplicates, not on your do-not-contact list. Adding keeps the contacts you already have.")),
    h("div", { class: "cols-2" }, field("Full name", inputs.name), field("Sequence", inputs.sequence, "Contacts join this sequence when you launch.")),
    h("div", { class: "cols-2" }, field("LinkedIn URL", inputs.linkedin_url, "The person's /in/ profile address."), field("Email (optional)", inputs.email)),
    h("div", { class: "cols-2" }, field("Company (optional)", inputs.company), field("Job title (optional)", inputs.title)),
    message, h("div", { class: "row" }, submit));
}
