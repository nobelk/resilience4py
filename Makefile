.PHONY: install clean build test lint format sort help

# Install dependencies
install:
	poetry install

# Clean build artifacts
clean:
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info

# Build the project
build: clean lint format sort test
	poetry build

# Run tests
test:
	poetry run pytest -ra

# Lint code using mypy
lint:
	poetry run flake8 --ignore=E501 src/*

# Format code using black
format:
	poetry run black .

# Sort imports using isort
sort:
	poetry run isort .

# Display help
help:
	@echo "Usage:"
	@echo "  make install    Install dependencies using Poetry"
	@echo "  make clean      Clean build artifacts"
	@echo "  make build      Clean, lint, format, sort, and build the project using Poetry"
	@echo "  make test       Run tests using pytest through Poetry"
	@echo "  make lint       Validate code using mypy through Poetry"
	@echo "  make format     Format code using black through Poetry"
	@echo "  make sort       Sort imports using isort through Poetry"
	@echo "  make help       Display this help message"