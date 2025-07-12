# Core Infrastructure Tests

This directory contains comprehensive unit tests for the resilience4py core infrastructure modules.

## Test Coverage

- **BaseConfig** (test_config.py): 12 tests
  - Configuration validation and immutability
  - Tags handling
  - Abstract base class behavior
  - Inheritance chains
  
- **Registry Pattern** (test_registry.py): 15 tests
  - Thread-safe instance management
  - Weak reference behavior
  - Configuration priority
  - Event consumer registration
  - Concurrent operations

- **Event System** (test_events.py): 20 tests
  - Event creation and inheritance
  - Async event publishing
  - Consumer registration/unregistration
  - Queue management and overflow handling
  - Error recovery
  - Context manager support

- **Decorators** (test_decorators.py): 24 tests
  - Sync/async function decoration
  - Exception propagation
  - Function metadata preservation
  - Composite decorator pattern
  - Nested decorations

- **Metrics** (test_metrics.py): 29 tests
  - Basic metrics collection
  - Sliding window metrics (count and time-based)
  - Statistical calculations (percentiles, averages)
  - Thread-safe operations
  - Metrics registry

## Running Tests

```bash
# Run all core tests
uv run python -m pytest tests/core/

# Run with coverage
uv run python -m pytest tests/core/ --cov=resilience4py.core

# Run specific test file
uv run python -m pytest tests/core/test_config.py

# Run specific test
uv run python -m pytest tests/core/test_config.py::TestBaseConfig::test_validation_called_on_init
```

## Test Requirements

- pytest >= 7.4.0
- pytest-asyncio >= 0.21.0
- pytest-cov >= 4.1.0
- pytest-mock >= 3.11.0

## Coverage Summary

Current test coverage: **96%** (328 statements, 14 missed)

The tests ensure:
- All abstract base classes are properly tested
- Thread safety and concurrent operations work correctly
- Async/await patterns are properly handled
- Edge cases and error conditions are covered
- Performance considerations (sliding windows, weak references)