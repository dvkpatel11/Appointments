# ── UsVisaAppointment — Makefile ──────────────────────────────────────────────
# Usage: make <target>
#
# Targets:
#   install      Set up virtual environment and install dependencies
#   playwright   Install Playwright browsers
#   run          Start the Canada Flask app locally
#   test         Run pytest
#   lint         Run ruff linter
#   format       Auto-format code with ruff
#   docker-build Build Docker image
#   docker-run   Run container locally on port 5000
#   deploy-gcp   Deploy to Google Cloud Run (requires gcloud auth)
#   backup       Backup JSON state files
#   clean        Remove caches, venv, build artifacts

PYTHON  ?= python3
VENV    ?= .venv
PORT    ?= 5000
IMAGE   ?= visa-ctrl

# ── Setup ─────────────────────────────────────────────────────────────────────
.PHONY: install
install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	@echo "Virtual environment ready: source $(VENV)/bin/activate"

.PHONY: playwright
playwright:
	$(VENV)/bin/playwright install --with-deps chromium

# ── Development ───────────────────────────────────────────────────────────────
.PHONY: run
run:
	FLASK_DEBUG=true PORT=$(PORT) $(VENV)/bin/python -m flask --app canada.app run --port $(PORT) --host 0.0.0.0

.PHONY: test
test:
	$(VENV)/bin/pytest tests/ -v

.PHONY: lint
lint:
	$(VENV)/bin/ruff check .

.PHONY: format
format:
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

# ── Docker ────────────────────────────────────────────────────────────────────
.PHONY: docker-build
docker-build:
	docker build -t $(IMAGE):latest .

.PHONY: docker-run
docker-run:
	docker run --rm -p $(PORT):8080 \
		--env-file .env \
		$(IMAGE):latest

# ── Deployment ────────────────────────────────────────────────────────────────
.PHONY: deploy-gcp
deploy-gcp:
	gcloud builds submit --config cloudbuild.yaml .

.PHONY: backup
backup:
	./scripts/backup.sh

# ── Cleanup ───────────────────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf $(VENV) __pycache__ .ruff_cache .pytest_cache .coverage
	rm -rf canada/__pycache__ uk/__pycache__
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	@echo "Cleaned."
