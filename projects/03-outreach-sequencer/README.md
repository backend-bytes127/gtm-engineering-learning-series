# Project 03: Outreach Sequencer

A small Email and LinkedIn sequencing tool. It takes a clean contact list, runs every contact through a multi-step sequence (emails, connection requests, DMs) and records every touch and reply in one place. Before anything goes live, every contact is checked, every message is personalised and checked, and the send limits and stop rules are set.

| | |
|---|---|
| Input | A clean contact list (CSV or XLSX). [Project 02's](../02-contact-list-merge/README.md) `Final_Contact_List.xlsx` imports as-is |
| Output | A tracker (status and touch log for every contact), `Sequence_Report.xlsx`, `Summary.md` |
| Result on the bundled synthetic sample | 36 rows read → 10 removed → 26 kept → 25 launched (1 held back for an unpersonalisable draft) → 86 messages over 3 weeks of simulated time |
| Quality gates | 475 tests, 98% coverage, golden-file regression, an independent SQL recount of every report number, lint |
| Stack | Python 3.10+, SQLite, openpyxl. No services, no API keys |
| **Sending is simulated** | Nothing is sent. See [what is and is not real](#what-is-and-is-not-real) |

## Try it

```bash
cd projects/03-outreach-sequencer
pip install -r requirements.txt
python3 -m sequencer demo        # import, validate, approve, launch, simulate 60 days, report -> output/
python3 -m pytest                # 475 tests
python3 -m sequencer serve       # the web app
```

`demo` is deterministic: the same command prints the same report every time, and the repository checks it against [`expected-output/`](expected-output/).

## Pictures

How it fits together, how a send is decided, and the code-level guardrails around the AI (Excalidraw sources are in [`docs/diagrams/`](../../docs/diagrams/)):

![Overview](../../docs/diagrams/outreach-sequencer-overview.png)
![Send decision](../../docs/diagrams/outreach-send-decision.png)
![AI guardrails](../../docs/diagrams/outreach-ai-guardrails.png)

The web app, on synthetic data only:

| Validate | Sequence | Messages |
|---|---|---|
| ![](docs/screens/validate.jpg) | ![](docs/screens/sequence.jpg) | ![](docs/screens/messages.jpg) |

| Launch checklist | Report | Inbox and AI settings |
|---|---|---|
| ![](docs/screens/launch.jpg) | ![](docs/screens/report.jpg) | ![](docs/screens/inbox.jpg) |

## The web app

```bash
python3 -m sequencer serve        # opens http://127.0.0.1:8765 (or: make sequencer-app)
```

A local interface with one screen per step of the brief, so the whole flow can be done without the command line:

| Screen | What you do there |
|---|---|
| 1 Import | Drop a CSV or XLSX, check the column matching (with example values), add a do-not-contact list |
| 2 Validate | See what was removed and why, filter by reason, review contacts that were kept with a note |
| 3 Build sequence | Add, reorder and remove steps; pick channel, wait days and message; problems show as you edit |
| 4 Write messages | Edit with live checks, insert variables, preview with a real contact, save, approve |
| 5 Sending rules | Daily limits, hours, days, timezone, stop rules, sender details, with a plain-words summary |
| 6 Launch & track | The launch checklist (each failure links to its fix), launch, run the simulation, open any contact's timeline and record what happened |
| 7 Report | KPIs, "what worked", by step and channel, Excel download |

It is a standard-library Python server plus plain HTML, CSS and JavaScript: no Node, no build step, no new dependencies, and it listens on `127.0.0.1` only. Data is kept in `output/web/`. The same engine runs underneath, so the app and the CLI give identical numbers (a test checks this).

Design notes: contact data is untrusted, so it only ever reaches the page as text; cross-origin writes are refused; every dialog and drawer traps focus and closes on Escape; status is never shown by colour alone; the layout works down to phone width.

## Hosting it and sending for real

The app can run on Railway behind a password, and send real LinkedIn invites and messages through [Unipile](https://www.unipile.com) to a short list you choose. Setup, variables, safety rails and what is and is not verified: [docs/DEPLOY.md](docs/DEPLOY.md).

- **Login:** one shared password (`APP_PASSWORD`). The server refuses to start on a public address without it.
- **Live mode is opt-in and fenced:** you pick up to 10 people, a preflight checks each on LinkedIn (and says whether an invite or a direct message will go), daily caps come from the environment, and a Stop button halts sending on the next tick.
- **Already connected?** The invite is skipped and the message goes straight out.
- **Replies** arrive by a signed webhook; accepted invites are found by polling your connection list.
- **AI assistant (optional):** Claude can draft each step and answer replies, in **Review** mode (you approve every message) or **Autonomous** mode (it sends within your limits), switchable any time from the Inbox page. The safety rules live in code, not prompts: opt-outs stop everything, pricing, legal and complaints go to you, there is a cap on automatic replies, and autonomous messages say an AI assistant wrote them. See [ADR-0010](../../docs/adr/0010-autonomous-ai-messaging-with-code-level-guardrails.md).
- The simulation stays available. A project is either simulated or live, never both.

## The seven steps, in code

| # | Brief | Module | What it does | Command |
|---|---|---|---|---|
| 1 | Import the list and map columns to the tool's fields | [`importer.py`](sequencer/importer.py) | Guesses the mapping from header names (`E-mail`, `Email ID`, `Work Email`...), lets you override any field, keeps the source row number of every contact | `import FILE --map name="Full Name"` |
| 2 | Validate; remove invalid, duplicate and opted-out records | [`validate.py`](sequencer/validate.py) | E-mail syntax, disposable and typo domains, role accounts; LinkedIn `/in/` URL check and normalising; duplicates by e-mail or LinkedIn; opt-outs from a status column or a suppression file. Removed records keep their reason | `import` |
| 3 | Build the sequence steps with wait days and channel | [`sequence.py`](sequencer/sequence.py) | Steps are `email`, `linkedin_invite`, `linkedin_message`; a DM needs an earlier invite; one invite per sequence; wait days 0-60 | `config` |
| 4 | Write templates with variables; check every draft before approval | [`templates.py`](sequencer/templates.py) | `{{first_name}}`, `{{company\|fallback}}`...; a linter (personalisation, unsubscribe line, invite length, spam phrases); a per-contact draft check; approval bound to a content hash | `lint`, `approve` |
| 5 | Set daily limits, hours and auto-stop rules | [`rules.py`](sequencer/rules.py), [`engine.py`](sequencer/engine.py) | Daily caps per channel, sending hours and weekdays in a timezone, stop on reply, bounce or meeting; hard ceilings the rules cannot exceed | `config`, `check`, `launch` |
| 6 | Track status and log every touch | [`store.py`](sequencer/store.py), [`engine.py`](sequencer/engine.py) | Not Started, In Sequence, Replied, Meeting Booked, Completed (plus Stopped); an append-only touch log and event log | `run`, `event`, `status` |
| 7 | Report by step and channel; share what worked | [`report.py`](sequencer/report.py) | Sent, opened, accepted, replied, meetings, with rates; a plain-language summary that refuses to over-claim | `report` |

Every module has a matching test file in [`sequencer/tests/`](sequencer/tests/).

## How a message gets sent

```
config + list ──> validate ──> approve templates ──> LAUNCH GATE ──> tick (every hour) ──> Provider.send
                                                      6 checks        window open?          │
                                                                      template still        ▼
                                                                      approved?          touch log
                                                                      under daily limit?     │
                       stop rules <── record_event <── replies, bounces, accepts, meetings <───┘
                       (status changes, next step cancelled, suppression list grows)
```

- **The launch gate** ([ADR-0008](../../docs/adr/0008-launch-gate-and-content-bound-approval.md)) refuses to start a sequence unless: contacts are validated, the sequence is well-formed, every template is approved *as it is now*, every draft personalises, the sender profile is set, and limits/hours/stop rules are set. `python3 -m sequencer check "Outbound Intro"` prints the checklist.
- **`tick`** runs once per simulated hour. It sends a step only if the window is open (hours and weekday, in the configured timezone), the template's approval hash still matches, and the channel is under its daily limit. Otherwise the step waits for the next tick, and the touch is not lost.
- **Skips** are logged, not silent: no e-mail on file, no LinkedIn URL, or a DM whose invite was never accepted within 14 days.
- **A LinkedIn DM** is sent only after the invite is accepted. Until then it waits.
- **Stop rules** apply the moment an event is recorded. Reply sets `Replied`, a booked meeting sets `Meeting Booked`, a bounce sets `Stopped` and adds the address to the suppression list. An **unsubscribe always stops**, even if the rules are narrowed.
- **A failed send** is logged and retried on the next tick, up to three attempts, then the contact is stopped as `send_failed`.

## What the demo shows

The bundled sample ([`sample-data/README.md`](sample-data/README.md) lists every planted defect) goes through the whole pipeline:

- **Validation:** 36 read, 26 kept, 10 removed (2 invalid e-mail, 2 duplicates, 4 opted out, 1 no reachable channel, 1 missing name). Two kept contacts lost one channel and stay reachable on the other.
- **The gate catches a real gap.** One kept contact has no company, and four templates use `{{company}}` with no fallback. A plain `launch` is refused and names the contact and the field. `--hold-incomplete` parks that one contact and launches the other 25.
- **Rules hold over 60 simulated days.** A test replays every sent message and asserts: inside the sending hours, on an active weekday, within the channel's daily limit, and never after the contact stopped. The demo's limits are low enough that the daily caps are actually reached.
- **The report is honest about small numbers.** With 4 replies in 86 messages, `Summary.md` says the channel gap is noise rather than naming a winner (`MIN_SAMPLE` messages and `MIN_REPLIES` replies are needed before it compares channels).

Full output: [`expected-output/Summary.md`](expected-output/Summary.md).

## Using your own list

```bash
python3 -m sequencer --db output/mine.sqlite import my_list.xlsx --sequence "Outbound Intro" --suppression my_dnc.csv
python3 -m sequencer --db output/mine.sqlite config --dir my_config/     # copy config/ and edit it
python3 -m sequencer --db output/mine.sqlite lint
python3 -m sequencer --db output/mine.sqlite approve
python3 -m sequencer --db output/mine.sqlite check "Outbound Intro"
python3 -m sequencer --db output/mine.sqlite launch "Outbound Intro" --hold-incomplete
python3 -m sequencer --db output/mine.sqlite run --days 30          # simulated; see below for real sending
python3 -m sequencer --db output/mine.sqlite event r0004 replied    # record something that happened
python3 -m sequencer --db output/mine.sqlite report
```

To chain from project 02, point `import` at its `Final_Contact_List.xlsx`; the headers map automatically.

The config folder holds four small JSON files: [`sequences.json`](config/sequences.json) (steps), [`templates.json`](config/templates.json) (copy), [`rules.json`](config/rules.json) (limits, hours, stop rules) and [`sender.json`](config/sender.json) (name and postal address for the e-mail footer).

## What is and is not real

**Real and tested:** import and column mapping, validation and de-duplication, template rendering and checks, the launch gate, scheduling, daily limits, sending windows, stop rules, status tracking, the touch log, suppression, reporting.

**Simulated:**

- **Sending.** By default `SimulatedProvider` sends nothing. Live LinkedIn sending exists (see above) but has only been tested against a faked Unipile, not yet against a real account.
- **Simulated provider.** `SimulatedProvider` sends nothing. Replies, bounces, opens, accepts and meetings come from a seeded random model with invented rates ([ADR-0009](../../docs/adr/0009-provider-interface-and-simulated-sending.md)). The report says so on its first line. To go live you implement one method, `Provider.send`, for a mailbox and a LinkedIn service, and call `engine.record_event` from their webhooks.
- **E-mail verification.** Checks are offline: syntax, disposable and typo domains, role accounts. They show an address is plausible, **not that the mailbox exists**. Confirming that needs an SMTP-level verification service; `validate.EmailVerifier` is the plug-in point.

**Known limits:**

- The web app's request handling is tested without a browser (every endpoint, plus the security cases), and the front end has guard tests for broken imports and unsafe HTML. Its look and feel was checked by hand in a browser, there are no automated browser tests, and `web/server.py` (the thin socket wrapper) has no automated test.
- The web app is single-user and local: no login, one project at a time. It is not meant to be put on a server.

- Sequences are linear, with no branching. A DM step waits for the invite to be accepted, so a contact who never accepts holds at that step for up to 14 days before the sequence moves on.
- One sender and one timezone; the contact's own timezone is not used.
- "Opened" is only meaningful for e-mail and, with real sending, depends on tracking pixels that many mail clients now block. Treat replies and meetings as the numbers to trust.
- `Stopped` is a sixth status beyond the brief's five, for bounces, opt-outs, failed sends and held contacts. Without it those people would be mislabelled `Completed`.

**Before real use:** automated LinkedIn activity can breach LinkedIn's terms and restrict the account; the default caps (8 invites and 15 messages per day) are conservative for that reason. E-mail needs a lawful basis in your jurisdiction. The tool adds an opt-out line and postal address to every e-mail and honours unsubscribes, but that is not legal advice.

## Borrowed from outbound-os

| Idea | There | Here |
|---|---|---|
| Step model | `email`, `linkedin_invite`, `linkedin_message` | the same three channels |
| Send policy as a pure verdict | hours, active days, daily caps, `BlockReason` | `rules.py`, `window_verdict`, with hard ceilings |
| A gate decision before any send | compliance gate, consent and suppression ledger | the launch gate and suppression list |
| Stop everywhere on a reply or opt-out | `effects.ts` | `engine.record_event` |
| Reply-based status | pipeline stages | the five statuses |

No code, keys or data were copied; only the concepts.

## Layout

```
projects/03-outreach-sequencer/
├── sequencer/             the package: importer, validate, sequence, templates, rules, store, engine, provider, simulate, report, workflow, cli
│   ├── web/               local web app: API (routes_*.py), server, and static/ (HTML, CSS, JS modules)
│   └── tests/             one test file per module, plus end-to-end tests on the sample
├── config/                sequences, templates, sending rules, sender, suppression list
├── sample-data/           synthetic contacts with planted defects, and a README listing them
├── expected-output/       golden metrics.json and Summary.md for the demo
└── scripts/make_sample_data.py   regenerates the sample list
```
