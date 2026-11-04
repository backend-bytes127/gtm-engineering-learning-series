# GTM Engineering Learning Series: common tasks. `make help` lists them.
P2 := projects/02-contact-list-merge
P1 := projects/01-linkedin-icp-scraper
PY ?= python3

.DEFAULT_GOAL := help
.PHONY: help install test lint parity secrets check build-workflows env hooks up down logs e2e guide

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

install:  ## install Python test dependencies
	$(PY) -m pip install -r $(P2)/requirements.txt ruff pytest-cov

test:  ## unit + integration + golden-file tests (Python reference build)
	cd $(P2) && $(PY) -m pytest --cov=pipeline --cov-report=term-missing --cov-fail-under=90

lint:  ## ruff
	ruff check $(P1)/scripts $(P2)

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

guide:  ## rebuild the HTML guide for Project 02
	cd $(P2)/docs/guide && $(PY) build_guide.py
