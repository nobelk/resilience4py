# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

resilience4py is a Python port of the Java Resilience4j library, designed to provide fault tolerance patterns (Circuit Breaker, Rate Limiter, Retry, Bulkhead) for Python applications. The project uses an async-first design with support for both synchronous and asynchronous functions.

## Development Environment

### Package Manager
This project uses `uv` package manager (version 0.7.13). All dependency management should be done through `uv`.

### Python Version
Requires Python >=3.10 (specified in `.python-version` file)

## Common Commands

### Dependency Management
```bash
# Install dependencies
uv pip install -e .

# Add a new dependency
uv add <package-name>

# Add a development dependency
uv add --dev <package-name>

# Update dependencies
uv lock --update-all
```

### Testing
```bash
# Run all tests (once test infrastructure is set up)
pytest

# Run tests with coverage
pytest --cov=resilience4py

# Run a specific test file
pytest tests/test_circuit_breaker.py

# Run tests matching a pattern
pytest -k "test_circuit_breaker"
```

### Code Quality
```bash
# Format code with black
black src/ tests/

# Run type checking
mypy src/

# Run linting
flake8 src/ tests/

# Run all quality checks
black src/ tests/ && flake8 src/ tests/ && mypy src/
```

## Architecture

### Planned Project Structure
```
src/resilience4py/
├── core/           # Base classes and utilities
│   ├── config.py          # Base configuration classes
│   ├── registry.py        # Generic registry pattern
│   ├── events.py          # Event system infrastructure
│   ├── decorators.py      # Base decorator utilities
│   └── metrics.py         # Metrics abstractions
├── circuitbreaker/ # Circuit breaker implementation
├── bulkhead/       # Bulkhead pattern
├── ratelimiter/    # Rate limiting
└── retry/          # Retry mechanism
```

### Key Design Principles
1. **Decorator Pattern**: All resilience patterns are implemented as Python decorators
2. **Async-First**: Built on asyncio with synchronous wrapper support
3. **Type Safety**: Extensive use of type hints and generics
4. **Immutable Configuration**: Configuration uses frozen dataclasses
5. **Event-Driven**: Async event system for monitoring and metrics

### Implementation Status
The project is currently in skeleton phase. The `claude-plan.md` file contains the detailed implementation plan from the Java migration. Key components to implement:

1. Core infrastructure (base classes, registry, events)
2. Circuit Breaker with state machine
3. Bulkhead (semaphore and thread pool variants)
4. Rate Limiter with atomic implementation
5. Retry with various backoff strategies

## Testing Approach

When implementing tests:
1. Use `pytest` with `pytest-asyncio` for async tests
2. Create unit tests for each component
3. Add integration tests for pattern composition
4. Include performance benchmarks
5. Test both sync and async function decorators

## Important Notes

- The project previously had a more complete structure (visible in git history) but has been reset to start fresh
- Follow the detailed migration plan in `claude-plan.md` for implementation guidance
- Maintain compatibility with both sync and async functions for all decorators
- Ensure thread safety using asyncio primitives
- Follow Python naming conventions (snake_case for functions/variables, PascalCase for classes)