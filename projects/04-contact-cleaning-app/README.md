# Project 04: Contact Cleaning App

A web app around [Project 02's](../02-contact-list-merge/README.md) cleaning and merge code. A person uploads the lead exports, the app cleans, standardizes and de-duplicates them, shows the consolidated list, and prepares a CRM update (HubSpot).

```
Upload files ──> Clean and standardize ──> Consolidate ──> CRM update
 (6 .xlsx)        (Project 02 pipeline)     (12 people)     (preview, then push)
```

| | |
|---|---|
| Input | The six source exports (Google Ads, event, LinkedIn form, scraped LinkedIn, Apollo, ZoomInfo) and an optional Rules template |
| Output | Final_Contact_List.xlsx, Cleaning_Audit.xlsx (both downloadable), and a CRM update plan |
| Result on the bundled synthetic sample | 37 rows → 5 removed → 32 kept → 12 people → 12 contacts, 5 companies, 12 links planned for the CRM |
| Quality gates | 56 tests, 96% coverage (CI gate 90%), lint, browser run on the sample |
| Stack | Python 3.10+, standard library server, plain JavaScript, openpyxl. No framework, no database |
| **CRM push is off by default** | The app shows a preview. See [CRM integration](#crm-integration) |

## Run it

```bash
cd projects/04-contact-cleaning-app
pip install -r requirements.txt
python3 -m contactapp            # http://127.0.0.1:8770  (or: make contact-app)
python3 -m pytest                # 56 tests
```

Click **Try the sample data** to see the whole flow with no files. The app reuses Project 02's `pipeline` package by path, so there is one copy of the cleaning rules.

## What each step does

1. **Upload.** One `.xlsx` per source. Every problem is reported at once (wrong file type, missing sheet, too large, missing file), so it is fixed in one pass.
2. **Clean and standardize.** Test and spam leads, hidden LinkedIn members and job seekers are removed with a reason. Names, titles, phones (E.164), e-mails, companies, sizes and locations are standardized by the Rules tab.
3. **Consolidate.** Records for the same person are grouped and merged (latest-dated employer and title, ZoomInfo then Apollo for company facts). The audit workbook shows every removal, merge and link decision.
4. **CRM update.** The consolidated list becomes a plan: which contacts and companies would be created or updated, which rows are skipped and why. Nothing is sent until push is enabled and confirmed.

## Hosting it (public demo, no login)

The deployed copy is a **public demo with no login**, so it is built to hold nothing:

- Each visitor gets an isolated, in-memory session (HttpOnly, SameSite=Strict, Secure cookie). Another visitor cannot see their data.
- Sessions are discarded after 30 minutes of inactivity; at most 100 are kept; runs are capped at 30 per minute across the server. Nothing is written to disk.
- **CRM push is unavailable there:** the server refuses to listen publicly if a HubSpot token is loaded. Run the push locally.
- A banner on the page tells visitors this, and asks them to use sample or non-personal data.

```bash
python3 deploy/stage.py /path/to/empty/folder   # copies only what the container needs
# the folder root holds Dockerfile-relative layout and railway.json; deploy it (Railway, or: docker build -f projects/04-contact-cleaning-app/Dockerfile .)
```

`/healthz` is the health check. The container runs as an unprivileged user and reads `PORT`.

## CRM integration

The plan is built by [`crm_plan.py`](contactapp/crm_plan.py) (pure, no network) and applied by [`hubspot.py`](contactapp/hubspot.py).

| Decision | Why |
|---|---|
| Contacts match on **e-mail**, companies on **domain** (batch upsert) | Running the same file twice updates records, it never duplicates them |
| **Blank fields are never sent** | A blank in our list can never erase a value that is already in the CRM |
| Rows with **no e-mail are skipped** and listed | They cannot be matched safely; a person decides |
| Company size bucket goes to a custom text property `gtm_company_size` | HubSpot's own field is a number; our value is a range such as `51-200` |
| Order: company upsert → contact upsert → read back ids → associate | Ids are read back by match key instead of trusting response order |
| Batches of 100, retry on 429 and 5xx | HubSpot's batch limit and rate limits |
| A failed stage **stops** the push and reports what was done | A partial result is never hidden |

**Safety rails for the real push** (all must hold):

- The app listens on `127.0.0.1` only, checks the `Host` header, and requires a per-run page token on every POST (blocks other web pages from calling it).
- The token is read in memory from an env file with `--crm-env-file`; only `HUBSPOT_TOKEN` and `HUBSPOT_PORTAL_ID` are read, and neither is shown, logged or returned by the API.
- The push button works only if the app was started with `--allow-crm-push`, and the person must type the number of contacts to confirm.
- If `HUBSPOT_PORTAL_ID` is in the env file, the app refuses to push when the token belongs to a different HubSpot account.

```bash
# preview only (default)
python3 -m contactapp
# real push: try a HubSpot developer test account first
python3 -m contactapp --crm-env-file /path/to/.env --allow-crm-push
```

**Rollout plan:** (1) preview against the sample; (2) push the sample to a HubSpot developer test account and check the records; (3) preview a real file and review the skipped rows; (4) push to the real account in a small batch first. Steps 2 and 4 are for a person to run: the tests use a fake transport and have not touched a live HubSpot account.

**Not built yet:** associating deals, updating owners, writing back a sync status, scheduled or webhook syncs, and a user login (the app is single-user and local).

## Layout

```
contactapp/
  intake.py      validate uploads, stage them under the names the pipeline expects
  service.py     run the Project 02 pipeline, return plain data and the two workbooks
  crm_plan.py    consolidated rows -> CRM plan (pure)
  hubspot.py     HubSpot client and the push (injectable transport)
  app.py         API routes and safety checks
  server.py      standard library HTTP server
  static/        the page (HTML, CSS, JavaScript; text inserted with textContent only)
  sessions.py    per-visitor in-memory sessions, expiry, run rate limit
  state.py       one visitor's result and CRM plan
  tests/
deploy/stage.py  stage a clean deploy folder
Dockerfile, railway.json
```
