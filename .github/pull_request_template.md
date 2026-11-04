## What and why

## Checklist
- [ ] `make check` passes locally
- [ ] Behavior change is made in both `pipeline/` (Python) and `n8n/src/` (JS), and `make parity` passes
- [ ] Workflow JSON regenerated with `make build-workflows` (not hand-edited)
- [ ] Golden files regenerated and the diff reviewed (if output changed)
- [ ] No secrets, tokens, personal data or unblurred screenshots
- [ ] ADR added for any non-obvious or hard-to-reverse decision
