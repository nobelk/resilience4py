# Circuit Breaker Tests

This directory contains comprehensive unit tests for the Circuit Breaker pattern implementation.

## Test Files

### test_config.py
Tests for `CircuitBreakerConfig` validation and configuration options:
- Default configuration values
- Custom configuration
- Validation of all parameters (thresholds, durations, window sizes)
- Exception recording logic with record/ignore lists and predicates
- Configuration immutability

### test_states.py
Tests for all Circuit Breaker states and transitions:
- **ClosedState**: Normal operation, threshold checking
- **OpenState**: Call rejection, automatic transition to half-open
- **HalfOpenState**: Limited permits, success/failure based transitions
- **DisabledState**: Always permits, no metrics
- **ForcedOpenState**: Always rejects calls
- **MetricsOnlyState**: Collects metrics without transitions
- Full state transition cycles and manual transitions

### test_metrics.py
Tests for metrics collection and sliding windows:
- **SlidingWindowMetrics**: Both count-based and time-based windows
- **HalfOpenMetrics**: Specialized metrics for half-open state
- Call outcome recording (success/failure, fast/slow)
- Window eviction policies
- Snapshot calculations (failure rate, slow call rate)
- Thread-safe concurrent operations
- Edge cases (zero duration, exact thresholds)

### test_circuit_breaker.py
Tests for the main `CircuitBreaker` class:
- Initialization and configuration
- Decorator functionality (async/sync functions)
- Execution flow and error handling
- State management and transitions
- Event emission
- Metrics collection
- Registry and singleton behavior
- Edge cases and concurrent operations

### test_events.py
Tests for the event system:
- All event types and their creation
- Event listener registration and removal
- Async event listeners
- Event emission in real scenarios
- Multiple listeners for same event
- Event timing accuracy

## Running Tests

To run all circuit breaker tests:
```bash
pytest tests/circuitbreaker/
```

To run a specific test file:
```bash
pytest tests/circuitbreaker/test_config.py
```

To run with coverage:
```bash
pytest tests/circuitbreaker/ --cov=resilience4py.circuitbreaker
```

To run specific test classes or methods:
```bash
# Run a specific test class
pytest tests/circuitbreaker/test_states.py::TestClosedState

# Run a specific test method
pytest tests/circuitbreaker/test_states.py::TestClosedState::test_acquire_permission_always_true
```

## Test Coverage

The tests cover:
- ✅ All state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- ✅ Failure rate threshold triggering
- ✅ Slow call detection and threshold triggering
- ✅ Both count-based and time-based sliding windows
- ✅ Async and sync function decoration
- ✅ Manual state transitions (reset, disable, force_open)
- ✅ Event emission for all event types
- ✅ Exception handling and ignored exceptions
- ✅ Concurrent call handling
- ✅ Edge cases and error conditions

## Notes

- Tests use `pytest-asyncio` for async test support
- Mock objects are used to isolate components
- Time-based tests use small delays to ensure reliability
- All tests are designed to be deterministic and fast