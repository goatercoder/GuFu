PY=.venv/bin/python
UVICORN=.venv/bin/uvicorn

.PHONY: setup start dev dev-fixture backend frontend test e2e build lint refresh dataset static static-test sp500 clean

setup:            ## create venv, install backend + frontend deps
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements-dev.txt
	cd frontend && npm install

start:            ## one-process app on http://127.0.0.1:8000 (same as double-clicking start.sh / start.command / start.bat)
	cd backend && ../$(PY) -m gufu.launch

backend:          ## run the API only (dev)
	cd backend && ../$(UVICORN) gufu.main:app --reload --port 8000

frontend:         ## run the Vite dev server (proxies /api to :8000)
	cd frontend && npm run dev

dev:              ## backend + frontend together
	@trap 'kill 0' INT TERM; \
	(cd backend && ../$(UVICORN) gufu.main:app --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

dev-fixture:      ## same, but offline on bundled sample data
	GUFU_FIXTURE_MODE=1 $(MAKE) dev

test:             ## backend unit + API tests
	cd backend && ../$(PY) -m pytest -q

lint:
	cd backend && ../.venv/bin/ruff check gufu tests
	cd frontend && npm run typecheck

build:            ## production frontend build (served by the backend from frontend/dist)
	cd frontend && npm run build

e2e:              ## Playwright smoke test (starts a fixture-mode backend itself)
	cd frontend && npx playwright test

refresh:          ## force a full data rebuild on a running backend
	curl -s -X POST "http://127.0.0.1:8000/api/admin/refresh?kind=all&force=true"

dataset:          ## build the full cache headlessly (needs GUFU_SEC_USER_AGENT); writes build/gufu-data.sqlite.gz
	$(PY) scripts/build_dataset.py --db build/gufu.sqlite --slim build/gufu-data.sqlite

static:           ## static edition (no backend) into frontend/dist + data, from build/gufu.sqlite
	cd frontend && VITE_STATIC_DATA=1 VITE_BASE=$${VITE_BASE:-/} npm run build
	$(PY) scripts/export_static.py --db build/gufu.sqlite --out frontend/dist/data

static-test:      ## offline copy of the static edition for `make e2e` (synthetic data)
	$(PY) scripts/build_dataset.py --fixture --db build/fixture.sqlite --slim ""
	cd frontend && VITE_STATIC_DATA=1 VITE_BASE=/GuFu/ npx vite build --outDir .static-site/GuFu --emptyOutDir
	$(PY) scripts/export_static.py --db build/fixture.sqlite --out frontend/.static-site/GuFu/data

sp500:            ## regenerate data/sp500.json from Wikipedia
	$(PY) scripts/refresh_sp500.py

clean:
	rm -rf backend/data/*.sqlite* frontend/dist frontend/test-results
