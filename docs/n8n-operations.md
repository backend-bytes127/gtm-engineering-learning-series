# n8n operations guide

Practical runbook for working with the local n8n instance, distilled from building both projects.

## Start, stop, reset

```bash
make up        # creates .env (with a random encryption key) and starts n8n at http://localhost:5678
make logs
make down      # stop, keep data
docker compose --env-file .env -f infra/docker-compose.yml down -v   # stop AND delete all data
```

On first visit n8n asks you to create an owner account. Form triggers and the CLI work without logging in.

## Import / export / publish cycle

Everything below runs inside the container (`docker exec gtm-n8n ...`) or with `docker cp` to move files.

```bash
# import (the JSON must contain an "id"; the CLI fails with NOT NULL constraint on workflow_entity.id otherwise)
docker cp projects/02-contact-list-merge/workflow/contact-list-merge.workflow.json gtm-n8n:/tmp/wf.json
docker exec gtm-n8n n8n import:workflow --input=/tmp/wf.json

# activate (production webhooks/forms only exist while a workflow is active)
docker exec gtm-n8n n8n publish:workflow --id=contactListMerge01
docker restart gtm-n8n          # publish only takes effect on restart

# export (then sanitize before committing)
docker exec gtm-n8n n8n export:workflow --id=<id> --output=/tmp/out.json
docker cp gtm-n8n:/tmp/out.json raw-export.json
python3 projects/01-linkedin-icp-scraper/scripts/sanitize_n8n_export.py raw-export.json workflow/x.workflow.json
```

Importing over an existing id replaces that workflow. Credentials referenced by name are not recreated; open the imported workflow and select your own credential on each node that needs one.

## Forms and webhook URLs

- A Form Trigger with a `webhookId` is served at `/form/<webhookId>`, **not** at the `path` parameter. Project 02's form is `/form/contact-merge-form-0001`.
- A multipart POST works for automation: each file field is named `field-0`, `field-1`, ... in the order the fields are defined. `scripts/e2e.py` does exactly this with the standard library.
- The *test* URL (`/form-test/...`) only works while the editor is listening. Use the production URL for repeatable runs.

## Where the output lives

- **Editor:** Executions tab → pick a run → open a node to see its input and output (Schema / Table / JSON). Item counts are printed on every connection.
- **Downloading a file:** open the Convert-to-File node of the run and download the binary.
- **Programmatically:** n8n stores executions in SQLite (`/home/node/.n8n/database.sqlite`) with the run data serialized by `flatted`. `projects/02-contact-list-merge/scripts/read_run.js` shows how to read the last run's `6 Final Output` items from inside the container. Treat this as a test aid, not a stable API; for production use n8n's REST API with an API key.

## Known gotchas

| Symptom | Cause | Fix |
|---|---|---|
| Extract From File returns 0 rows for a sheet that has title rows | `range: "A5"` is parsed as the single cell A5 | Use a **numeric** range (`"4"` skips four rows) |
| A stray character (`U+F680`) after names that had an emoji | The bundled xlsx reader decodes 4-byte emoji into private-use code points | Strip `\uE000-\uF8FF` along with emoji when cleaning text |
| `NOT NULL constraint failed: workflow_entity.id` on import | Export was stripped of `id` | Keep an `id` in the JSON |
| Form completion page redirects to a dead host | The Form *ending* node and the waiting page use `WEBHOOK_URL`; if it points at a stale tunnel (e.g. an expired ngrok URL) the redirect breaks | Set `WEBHOOK_URL` correctly, or avoid the ending node and return the file from the execution |
| "Lost connection to the server" in the editor behind nginx | A proxy passing `Host: localhost` without the port makes n8n reject the websocket origin | Use `proxy_set_header Host $http_host;` |
| "Workflow has issues: Parameter ... is required" at run time | A node was imported with a required parameter empty (e.g. Form ending needs a Completion Title) | Open the node in the editor; the red marker shows what is missing |
| Google Sheets: "No columns found" | The target tab has no header row | Create row 1 headers (or use a tab that already has them) |
| Google Sheets: "API has not been used in project ..." | The Sheets API is not enabled in the Google Cloud project that owns the OAuth client | Enable it once in the Cloud console |
| Apify: "free user run limit reached" | Some actors cap Free-plan users | Pick an actor without a free-tier cap, or upgrade (see Project 01) |
| Re-running a flow duplicates rows | Google Sheets *append* is not idempotent | Use append-or-update keyed on a stable id |

## Debugging checklist

1. Re-run with the **same input** and open the first node whose output looks wrong; counts on the connections show where rows are lost.
2. For a Code node, `console.log` writes to the browser console in the editor and to the container log for production runs.
3. Reproduce locally without Docker: `python3 projects/02-contact-list-merge/n8n/dump_sheets.py sheets.json` then `node n8n/harness.mjs <workflow.json> sheets.json <outdir>`.
4. If behavior differs between the harness and n8n, the difference is in an n8n node (Extract From File, Merge, IF, Convert To File), not in your Code node. Compare the item counts and field types of that node's output.
