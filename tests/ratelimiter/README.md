# Rate Limiter Tests

This directory contains comprehensive unit and integration tests for the rate limiter pattern implementation.

## Test Structure

- **test_config.py**: Tests for RateLimiterConfig validation and configuration management
- **test_atomic_rate_limiter.py**: Tests for the core AtomicRateLimiter algorithm including:
  - Permission reservation and cycle refresh
  - Nanosecond precision timing
  - Concurrent access handling
  - Event publishing
  - Decorator functionality
  
- **test_rate_limiter.py**: Tests for the high-level RateLimiter class including:
  - Registry pattern functionality
  - Decorator usage (sync and async)
  - Shared instance management
  - Convenience functions
  
- **test_events.py**: Tests for rate limiter event classes and event handling
  
- **test_integration.py**: Integration tests covering:
  - End-to-end rate limiting scenarios
  - Concurrent request handling
  - Multiple rate limiter composition
  - Thread safety
  - Performance and timing precision

## Running Tests

To run all rate limiter tests:

```bash
# Install test dependencies
uv pip install -e ".[test]"

# Run all tests
pytest tests/ratelimiter/

# Run with coverage
pytest tests/ratelimiter/ --cov=resilience4py.ratelimiter

# Run specific test file
pytest tests/ratelimiter/test_atomic_rate_limiter.py

# Run specific test
pytest tests/ratelimiter/test_config.py::TestRateLimiterConfig::test_validation_limit_for_period

# Run with verbose output
pytest tests/ratelimiter/ -v

# Skip slow tests
pytest tests/ratelimiter/ -m "not slow"
```

## Test Coverage

The tests cover:

1. **Configuration Validation**: All configuration parameters and their constraints
2. **Core Algorithm**: Permission reservation, cycle refresh, timeout handling
3. **Concurrency**: Thread-safe operations and concurrent request handling
4. **Timing Precision**: Nanosecond-level timing accuracy
5. **Event System**: Event creation, publishing, and handling
6. **Decorator Pattern**: Both sync and async function decoration
7. **Registry Pattern**: Shared instance management
8. **Error Handling**: Proper exception propagation and handling
9. **Integration**: Real-world usage scenarios and pattern composition

## Key Test Scenarios

- Basic rate limiting with immediate success/failure
- Rate limiting with waiting and timeout
- Concurrent access from multiple threads/coroutines
- Cycle refresh and permission replenishment
- Multiple rate limiters on the same function
- Direct permission acquisition without decorators
- Metrics tracking and reset functionality
- Event publishing for monitoring

## Notes

- Tests use mocking for time-sensitive operations to ensure reliability
- Integration tests include actual timing verification with tolerances
- Thread safety test uses ThreadPoolExecutor to verify concurrent behavior
- All async tests are properly marked with `@pytest.mark.asyncio`