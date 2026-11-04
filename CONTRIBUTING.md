# Contributing

## Workflow

1. Branch from `main`: `feat/...`, `fix/...`, `docs/...`.
2. `make hooks` once per clone, so secrets are blocked before they are committed.
3. Make the change, then run `make check`. It is exactly what CI runs.
4. Open a pull request using the template. CI must be green.

## Commit messages

```
<type>: <description>

<optional body explaining why>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`.

## Conventions

- **Tests first.** Add a failing test for the behavior, then the implementation. Keep coverage at or above 90% (`make test` enforces it).
- **Golden files.** If a rule change legitimately changes the output, regenerate `expected-output/` and review the diff in the pull request. Never edit a golden file by hand.
- **One source of truth for workflow logic.** Edit `projects/02-contact-list-merge/n8n/src/*.js`, then `make build-workflows`. Never edit the generated workflow JSON by hand. CI fails if it is stale.
- **Behavior change in two places.** Python (`pipeline/`) and JavaScript (`n8n/src/`) implement the same rules. Change both and run `make parity`.
- **Immutability.** Prefer returning new objects over mutating inputs.
- **Record decisions.** A choice that is non-obvious or hard to reverse gets an ADR in `docs/adr/` (copy the template in `docs/adr/README.md`).

## Adding a project

Create `projects/NN-name/` with: `README.md` (problem, design, how to run, results, problems hit), `workflow/` (sanitized n8n export), `data/` or `sample-data/` (synthetic only), tests, and add it to the table in the root README. Export workflows with `n8n export:workflow` and run them through `sanitize_n8n_export.py`.

## Screenshots

Screenshots are welcome in docs, but anything showing people, e-mail addresses, phone numbers, URLs of private sheets or account names must be pixelated before commit. Keep unblurred originals outside the repo.
