# GTM Engineering Learning Series: common tasks. `make help` lists them.
P2 := projects/02-contact-list-merge
P1 := projects/01-linkedin-icp-scraper
P3 := projects/03-outreach-sequencer projects/04-contact-cleaning-app
P4 := projects/04-contact-cleaning-app
PY ?= python3

.DEFAULT_GOAL := help
.PHONY: help install test lint parity secrets check build-workflows env hooks up down logs e2e guide notebook notebook-test sequencer-demo sequencer-app contact-app

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

install:  ## install Python test dependencies
	$(PY) -m pip install -r $(P2)/requirements.txt ruff pytest-cov

test:  ## unit + integration + golden-file tests (projects 02, 03 and 04)
	cd $(P2) && $(PY) -m pytest --cov=pipeline --cov-report=term-missing --cov-fail-under=90
	cd $(P3) && $(PY) -m pytest --cov=sequencer --cov-report=term-missing --cov-fail-under=90
	cd $(P4) && $(PY) -m pytest --cov=contactapp --cov-report=term-missing --cov-fail-under=90

lint:  ## ruff
	ruff check $(P1)/scripts $(P2) $(P3) $(P4)

parity:  ## n8n JavaScript nodes must reproduce the Python golden output exactly
	cd $(P2) && $(PY) scripts/parity_check.py

secrets:  ## fail on secrets / private identifiers / forbidden files
	$(PY) scripts/check_no_secrets.py

build-workflows:  ## regenerate the Contact List Merge workflow JSON from n8n/src
	cd $(P2) && $(PY) n8n/build_workflow.py

check: lint test build-workflows parity secrets  ## everything CI runs
	@git diff --exit-code -- $(P2)/workflow || (echo "workflow JSON is stale: commit the rebuilt file" && exit 1)

env:  ## create .env with a fresh encryption key (once)
	@test -f .env || (cp .env.example .env && sed -i.bak "s/^N8N_ENCRYPTION_KEY=.*/N8N_ENCRYPTION_KEY=$$(openssl rand -hex 32)/" .env && rm -f .env.bak && echo "created .env")

hooks:  ## enable the pre-commit secret scan for this clone
	git config core.hooksPath .githooks

up: env  ## start local n8n (infra/docker-compose.yml)
	docker compose --env-file .env -f infra/docker-compose.yml up -d

down:  ## stop local n8n (keeps the data volume)
	docker compose --env-file .env -f infra/docker-compose.yml down

logs:  ## follow n8n logs
	docker logs -f gtm-n8n

e2e:  ## import + run Contact List Merge in the n8n container, compare to golden
	cd $(P2) && $(PY) scripts/e2e.py --port $${N8N_HOST_PORT:-5678}

notebook:  ## build, run and tidy the walkthrough notebook + HTML export (needs requirements-notebook.txt)
	cd $(P2)/notebooks && $(PY) make_walkthrough.py && $(PY) -m jupyter nbconvert --to notebook --execute --inplace walkthrough.ipynb && $(PY) finalize_notebook.py && $(PY) -m jupyter nbconvert --to html walkthrough.ipynb

notebook-test:  ## run the notebook as a test: fails if any cell errors
	cd $(P2) && $(PY) -m pytest --nbmake notebooks/walkthrough.ipynb

sequencer-demo:  ## project 03: run the whole pipeline on the sample data (simulated sending) -> output/
	cd $(P3) && $(PY) -m sequencer demo

sequencer-app:  ## project 03: open the web app on http://127.0.0.1:8765
	cd $(P3) && $(PY) -m sequencer serve

guide:  ## rebuild the HTML guide for Project 02
	cd $(P2)/docs/guide && $(PY) build_guide.py

contact-app:  ## project 04: contact cleaning web app on http://127.0.0.1:8770 (CRM preview only)
	cd $(P4) && $(PY) -m contactapp
