NODE_ENV := $(CURDIR)/.nodeenv
NODE_ENV_BIN := $(NODE_ENV)/bin

PRUNE_INACTIVE_FEEDS = src/feed/output/feeds_to_prune.txt
CONFIG_FILE = src/feed/config.ini
TEMP_FILE = src/feed/config_temp.ini

.PHONY: help
help:  ## Display this message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

.PHONY: install-uv
install-uv:  ## Install uv
	@echo "Installing uv..."
	@if [ "$(OS)" = "Windows_NT" ]; then \
		powershell -c "irm https://astral.sh/uv/install.ps1 | iex"; \
	else \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	@echo "Done"

.PHONY: install build-css
install:  ## Install dependencies
	@if ! uv --version > /dev/null; then $(MAKE) install-uv; fi
	@echo "Installing dependencies..."
	@uv sync
	@echo "Done"

.PHONY: fmt
fmt:  ## Format the code
	@echo "Formatting code..."
	@uv run ruff format

	@if [ ! -d "$(NODE_ENV)" ]; then \
		echo "Installing frontend dependencies..."; \
		$(MAKE) build-css; \
	fi
	@. $(NODE_ENV_BIN)/activate && \
	if ! npm list prettier > /dev/null 2>&1; then \
		echo "Installing Prettier..."; \
		npm install; \
	fi

	npm run format
	@echo "Done"

.PHONY: lint
lint:  ## Lint the code
	@echo "Linting code..."
	@uv run ruff check --fix
	@echo "Done"

.PHONY: ci
ci: fmt lint ## Run CI checks

.PHONY: build-css
build-css:  ## Build Tailwind CSS
	@echo "Building Tailwind CSS..."
	@$(MAKE) install

	@if [ ! -d "$(NODE_ENV)" ]; then \
		@uv run nodeenv --node=22.6.0 $(NODE_ENV); \
	fi
	@. $(NODE_ENV_BIN)/activate && \
	if [ ! -d "node_modules" ]; then \
		@npm install; \
	fi && \

	@npx tailwindcss -i ./src/styles/tailwind.css -o ./src/feed/output/styles.css
	@echo "Done"

.PHONY: watch-css
watch-css:  ## Run Tailwind with hot reload
	@echo "Running Tailwind with hot reload... Press Ctrl+C to stop"
	@npx tailwindcss -i ./src/styles/tailwind.css -o ./src/feed/output/styles.css --watch

.PHONY: build
build:  install ## Build the project
	@echo "Building project..."
	@uv run src/feed/feed.py
	@echo "Done"

.PHONY: prune-feeds
prune-feeds:  ## Prune inactive feeds
	@cp $(CONFIG_FILE) $(TEMP_FILE)
	@while read -r url; do \
		sed -i '' "\|$$url|,+1d" $(TEMP_FILE); \
	done < $(PRUNE_INACTIVE_FEEDS)
	@mv $(TEMP_FILE) $(CONFIG_FILE)