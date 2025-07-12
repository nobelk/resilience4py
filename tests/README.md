# Resilience4py Tests

This directory contains the test suite for the resilience4py library.

## Structure

The test directory structure mirrors the source code structure:

```
tests/
├── core/           # Tests for core infrastructure
├── circuitbreaker/ # Tests for circuit breaker pattern
├── bulkhead/       # Tests for bulkhead pattern
├── ratelimiter/    # Tests for rate limiting
├── retry/          # Tests for retry pattern
└── conftest.py     # Shared pytest fixtures
```

## Running Tests

### Install test dependencies
```bash
uv pip install -e ".[test]"
```

### Run all tests
```bash
pytest
# or
make test
```

### Run specific test categories
```bash
# Unit tests only
pytest -m unit
# or
make test-unit

# Integration tests only
pytest -m integration
# or
make test-integration

# Slow tests
pytest -m slow
# or
make test-slow
```

### Run with coverage
```bash
pytest --cov=resilience4py --cov-report=html
# or
make coverage
```

### Run tests for a specific module
```bash
pytest tests/circuitbreaker/
pytest tests/retry/test_config.py
pytest -k "test_circuit_breaker"
```

## Test Categories

Tests are marked with the following categories:

- `@pytest.mark.unit` - Unit tests that test individual components in isolation
- `@pytest.mark.integration` - Integration tests that test component interactions
- `@pytest.mark.slow` - Tests that take longer to run (> 1 second)
- `@pytest.mark.asyncio` - Tests that use asyncio (automatically detected)

## Writing Tests

### Test Fixtures

Common test fixtures are available in `conftest.py`:

- `mock_time` - Mock time.time() for deterministic testing
- `mock_async_time` - Mock asyncio.sleep() and time for async tests
- `failing_function` - A function that always raises an exception
- `async_failing_function` - An async function that always raises an exception
- `successful_function` - A function that always returns successfully
- `async_successful_function` - An async function that always returns successfully
- `slow_function` - A function that simulates slow execution
- `async_slow_function` - An async function that simulates slow execution
- `flaky_function` - A function that fails intermittently
- `async_flaky_function` - An async function that fails intermittently
- `event_collector` - Collects events for verification
- `mock_registry` - Mock registry for testing

### Example Test

```python
import pytest
from resilience4py.retry import Retry, RetryConfig

@pytest.mark.unit
class TestRetry:
    def test_successful_call(self, successful_function):
        """Test retry with a successful function."""
        config = RetryConfig(max_attempts=3)
        retry = Retry(config)
        
        decorated = retry(successful_function)
        result = decorated()
        
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_async_retry(self, async_flaky_function):
        """Test retry with an async function that fails then succeeds."""
        config = RetryConfig(max_attempts=3)
        retry = Retry(config)
        
        decorated = retry(async_flaky_function)
        result = await decorated(fail_times=2)
        
        assert "Success" in result
```

## Coverage Goals

We aim for:
- 90%+ overall code coverage
- 100% coverage of critical paths (state transitions, error handling)
- All public APIs must have tests
- Edge cases and error conditions must be tested