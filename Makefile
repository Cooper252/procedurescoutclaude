PY ?= .venv/bin/python
include $(wildcard .env)
export

.PHONY: setup up down migrate downgrade test lint typecheck check api reference-nv reference-report

setup:            ## create virtualenv and install pinned dependencies
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

up:               ## start PostgreSQL/PostGIS (and MinIO) in Docker
	docker compose up -d --wait

down:
	docker compose down

migrate:          ## apply all migrations to the dev database
	$(PY) -m alembic upgrade head

downgrade:        ## roll the dev database back to empty
	$(PY) -m alembic downgrade base

test:             ## run the full test suite against TEST_DATABASE_URL
	$(PY) -m pytest

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

typecheck:
	$(PY) -m mypy

check: lint typecheck test

api:              ## run the API locally on port 8000
	$(PY) -m uvicorn procedurescout_api.main:app --app-dir apps/api --reload

reference-nv:     ## load Nevada facility + code reference data (needs internet; AHRQ=path-or-url optional)
	PYTHONPATH=packages/core:packages/ingest $(PY) -m procedurescout_ingest.reference.cli nv-all --state NV $(if $(AHRQ),--ahrq-file $(AHRQ))

reference-report: ## counts of loaded reference data for Nevada
	PYTHONPATH=packages/core:packages/ingest $(PY) -m procedurescout_ingest.reference.cli report --state NV
