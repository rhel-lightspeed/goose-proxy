.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: dev
dev: ## Run development API
	uv run --locked flask --app goose_proxy.app:app run --debug --reload

.PHONY: test
test: ## Run tests
	uv run --locked pytest

.PHONY: lint
lint: ## Run linter checks
	uv run --locked ruff check src/ tests/

.PHONY: check
check: ## Run ty checks
	uv run --locked ty check src

.PHONY: format
format: ## Format code
	uv run --locked ruff format src/ tests/

.PHONY: man
man: ## Build man pages with Sphinx
	uv run sphinx-build -b man docs/man docs/build/man

.PHONY: clean
clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info src/*.egg-info docs/build
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +

.PHONY: request
request: ## Make a test request to the v1 API
	@curl -sX POST localhost:8000/v1/chat/completions \
		-H "Content-Type: application/json" \
		--data '{"model": "", "messages": [{"role": "user", "content": "How do I enable SSH root login on RHEL?"}], "stream": false}' | jq
