PYTHON  ?= python3
VENV    ?= env
PORT    ?= 5000
IMAGE   ?= visa-ctrl

.PHONY: install
install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/playwright install --with-deps chromium
	@echo "Virtual environment ready: source $(VENV)/bin/activate"

.PHONY: playwright
playwright:
	$(VENV)/bin/playwright install --with-deps chromium

.PHONY: run
run:
	FLASK_DEBUG=true PORT=$(PORT) $(VENV)/bin/python run.py

.PHONY: test
test:
	$(VENV)/bin/pytest tests/ -v

.PHONY: lint
lint:
	$(VENV)/bin/ruff check src/

.PHONY: format
format:
	$(VENV)/bin/ruff check --fix src/
	$(VENV)/bin/ruff format src/

.PHONY: docker-build
docker-build:
	docker build -t $(IMAGE):latest .

.PHONY: docker-run
docker-run:
	docker run --rm -p $(PORT):8080 \
		--env-file .env \
		$(IMAGE):latest

.PHONY: deploy-gcp
deploy-gcp:
	gcloud builds submit --config cloudbuild.yaml .

.PHONY: clean
clean:
	rm -rf __pycache__ .ruff_cache .pytest_cache .coverage
	rm -rf src/__pycache__ src/*/__pycache__ src/*/*/__pycache__
	find . -path ./env -prune -o -name "*.pyc" -print -delete
	find . -path ./env -prune -o -name "*.pyo" -print -delete
	@echo "Cleaned."
