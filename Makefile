.PHONY: help install install-dev sync test test-unit test-integration test-slow coverage lint format type-check clean build

help:
	@echo "Available commands:"
	@echo "  make install        Install the package"
	@echo "  make install-dev    Install with development dependencies"
	@echo "  make sync          Sync all dependencies from lock file"
	@echo "  make test          Run all tests"
	@echo "  make test-unit     Run unit tests only"
	@echo "  make test-integration Run integration tests only"
	@echo "  make test-slow     Run slow tests"
	@echo "  make coverage      Run tests with coverage report"
	@echo "  make lint          Run code linting"
	@echo "  make format        Format code with black and isort"
	@echo "  make type-check    Run type checking with mypy"
	@echo "  make build         Build the package"
	@echo "  make clean         Clean up generated files"

install:
	uv pip install -e .

install-dev:
	uv sync --dev

sync:
	uv sync

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

test-slow:
	uv run pytest -m slow

coverage:
	uv run pytest --cov=resilience4py --cov-report=term-missing --cov-report=html

lint:
	uv run flake8 src/ tests/

format:
	uv run black src/ tests/
	uv run isort src/ tests/

type-check:
	uv run mypy src/

build:
	uv build

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name "dist" -exec rm -rf {} +
	find . -type f -name "coverage.xml" -delete