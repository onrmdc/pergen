PY ?= python3
PIP ?= $(PY) -m pip

.PHONY: help install install-dev test test-fast lint lint-fix cov cov-new clean run e2e e2e-install

help:
	@echo "Pergen — make targets"
	@echo "  install      Install runtime dependencies"
	@echo "  install-dev  Install runtime + dev dependencies"
	@echo "  test         Run the full test suite"
	@echo "  test-fast    Run only unit-marked tests"
	@echo "  lint         Run ruff (check only)"
	@echo "  lint-fix     Run ruff with --fix"
	@echo "  cov          Run tests with global coverage report (gate: 45% — legacy modules drag the average down)"
	@echo "  cov-new      Run tests with coverage scoped to the new OOD layer (gate: 85%)"
	@echo "  run          Start the Flask dev server (FLASK_APP=backend.app)"
	@echo "  clean        Remove caches and bytecode"

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements-dev.txt

test:
	$(PY) -m pytest

test-fast:
	$(PY) -m pytest -m unit

lint:
	$(PY) -m ruff check .

lint-fix:
	$(PY) -m ruff check . --fix

cov:
	$(PY) -m pytest --cov=backend --cov-report=term-missing --cov-fail-under=45

# Scoped coverage of the new OOD layer (services / repositories / blueprints
# / runner factory + concrete runner classes / security / parsers / config /
# app_factory / logging_config / request_logging).  Held to 85% because the
# legacy backend modules (app.py, find_leaf.py, nat_lookup.py,
# route_map_analysis.py) are intentionally untouched in this PR.
cov-new:
	$(PY) -m pytest \
	  --cov=backend.services --cov=backend.repositories --cov=backend.blueprints \
	  --cov=backend.runners.factory --cov=backend.runners.base_runner \
	  --cov=backend.runners.arista_runner --cov=backend.runners.cisco_runner \
	  --cov=backend.runners.ssh_runner_class \
	  --cov=backend.security --cov=backend.parsers --cov=backend.config \
	  --cov=backend.app_factory --cov=backend.logging_config --cov=backend.request_logging \
	  --cov-report=term-missing --cov-fail-under=85

run:
	FLASK_APP=backend.app $(PY) -m flask run

clean:
	@find . -type d -name __pycache__ -not -path "./venv/*" -not -path "./.venv/*" -not -path "./vendor_pkgs/*" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache htmlcov .coverage coverage.xml

# ----------------------------------------------------------------------
# E2E tests (Playwright + real Flask server)
#
# `make e2e` boots the dev server via run.sh (through Playwright's
# webServer config), runs the Playwright suite, and tears the server
# down on exit. Reports land in ./playwright-report and ./test-results.
# ----------------------------------------------------------------------
e2e-install:
	npm install
	npx playwright install chromium

e2e:
	npx playwright test --reporter=list
