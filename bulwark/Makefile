# Bulwark — CMMC Level 2 compliance automation
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help setup dev run test lint build catalog seed clean docker

help:
	@echo "make setup     install backend and frontend dependencies"
	@echo "make run       build the frontend and serve everything on http://127.0.0.1:8800"
	@echo "make dev       backend on :8800 (run 'cd frontend && npm run dev' beside it)"
	@echo "make test      backend and agent test suites"
	@echo "make lint      ruff over the backend and the agent"
	@echo "make build     typecheck and build the frontend"
	@echo "make catalog   rebuild catalog/cmmc_l2_catalog.json from its sources"
	@echo "make seed      load the demo machine shop into the local database"

$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install -q -U pip

setup: $(VENV)
	$(PIP) install -q -r backend/requirements-dev.txt
	cd frontend && npm install --no-audit --no-fund

dev: $(VENV)
	cd backend && ../$(PY) -m uvicorn bulwark.main:app --reload --port 8800

run: build
	cd backend && ../$(PY) -m uvicorn bulwark.main:app --host 127.0.0.1 --port 8800

test: $(VENV)
	$(PY) catalog/build_catalog.py --check
	cd backend && ../$(PY) -m pytest -q
	$(PY) -m pytest agent/tests -q

lint: $(VENV)
	$(PY) -m ruff check backend/bulwark backend/tests agent

build:
	cd frontend && npm run build

catalog:
	$(PY) catalog/build_catalog.py

seed: $(VENV)
	cd backend && ../$(PY) -c "from bulwark.db import init_db, get_engine; from sqlmodel import Session; from bulwark.seed import seed_demo; init_db(); s=Session(get_engine()); print(seed_demo(s))"

clean:
	rm -rf backend/data frontend/dist frontend/node_modules $(VENV)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

docker:
	docker compose up --build
