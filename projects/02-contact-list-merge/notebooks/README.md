# Walkthrough notebook

[`walkthrough.ipynb`](walkthrough.ipynb) walks through every stage of the Contact List Merge on the bundled synthetic sample, showing the data before and after each step, with charts and short explanations of *why* each rule exists. GitHub renders it in the browser, outputs included. A static HTML copy is [`walkthrough.html`](walkthrough.html) (also on the project site).

| Section | You see |
|---|---|
| 0 Raw data | the exports as they arrive, and rows per source |
| 1 Map columns | one common record shape, parsed dates |
| 2 Clean + validate | what was removed and why |
| 3 Standardize | raw next to standardized values; **evidence for which phone columns to trust** |
| 4 Group people | records linked into people (graphs), the logged decisions, and the guard that refuses to merge two LinkedIn identities |
| 5 Merge | one row per person; a job changer resolved by the latest dated source; provenance and review flags |
| 6 Verify | identical to the golden file; identical to the n8n JavaScript |

The notebook **imports the tested `pipeline/` package** rather than re-implementing it, so it cannot drift from the real logic.

## Run it

Use a virtual environment (a conflicting NumPy in a global install is the usual source of trouble):

```bash
cd projects/02-contact-list-merge
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-notebook.txt
jupyter lab notebooks/walkthrough.ipynb      # Node 20+ is optional, for the JS parity cell
```

## Files

| File | Purpose |
|---|---|
| `make_walkthrough.py` | generates the notebook; the narrative and code live here as reviewable text |
| `finalize_notebook.py` | tidies an executed notebook (portable kernel name, no environment noise) |
| `walkthrough.ipynb` | the executed notebook, committed with outputs |
| `walkthrough.html` | static export for the project site |

Rebuild everything with `make notebook` from the repo root. `make notebook-test` runs the notebook as a test (CI does the same): it fails if any cell errors, including the cell that asserts the output equals the golden file and the n8n JavaScript.
