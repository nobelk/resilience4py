# resilience4py

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-44%25-yellow)](htmlcov/index.html)

resilience4py is a Python port of the popular Java library [resilience4j](https://github.com/resilience4j/resilience4j), providing fault tolerance patterns for building resilient applications.

## What is resilience4py?

Resilience4py is a lightweight fault tolerance library designed for functional programming in Python. It provides higher-order functions (decorators) to enhance any functional interface, lambda expression, or method reference with resilience patterns such as Circuit Breaker, Rate Limiter, Retry, and Bulkhead.

Unlike other fault tolerance libraries, Resilience4py is designed to be modular, allowing developers to choose only the patterns they need. The library has minimal dependencies and is built with a functional programming approach using modern Python features like asyncio and type hints.

## Installation

### Prerequisites

- Python 3.10 or higher
- [uv package manager](https://github.com/astral-sh/uv) (recommended) or pip

### Install from source

```bash
# Clone the repository
git clone https://github.com/nobelk/resilience4py.git
cd resilience4py

# Install using uv (recommended)
uv pip install -e .

# Or install using pip
pip install -e .
```

### Install dependencies for development

```bash
# Install with test dependencies
uv pip install -e ".[test]"

# Or install development dependencies
uv add --dev pytest-asyncio pytest-cov pytest-timeout pytest-mock
```

## Quick Start

```python
from resilience4py import CircuitBreaker, RateLimiter, Retry, Bulkhead
from resilience4py.circuitbreaker import CircuitBreakerConfig
from resilience4py.ratelimiter import RateLimiterConfig
from resilience4py.retry import RetryConfig
from resilience4py.bulkhead import BulkheadConfig

# Circuit Breaker example
@CircuitBreaker("my-service", CircuitBreakerConfig(
    failure_rate_threshold=50.0,
    sliding_window_size=100
))
async def protected_api_call():
    return await external_api.fetch_data()

# Rate Limiter example
@RateLimiter("api-limiter", RateLimiterConfig(
    limit_for_period=100,
    limit_refresh_period=timedelta(seconds=1)
))
def rate_limited_function():
    return expensive_operation()

# Retry example
@Retry("flaky-service", RetryConfig(
    max_attempts=3,
    wait_duration=timedelta(seconds=1)
))
async def flaky_operation():
    return await unreliable_service.call()

# Bulkhead example
@Bulkhead("resource-pool", BulkheadConfig(
    max_concurrent_calls=10
))
def resource_intensive_task():
    return process_data()
```

## Resilience Patterns

### Circuit Breaker
The Circuit Breaker pattern prevents an application from repeatedly executing an operation that's likely to fail. It monitors for failures and trips when a threshold is reached, preventing further calls to the failing operation.

**Key characteristics:**
- Operates as a state machine (CLOSED → OPEN → HALF_OPEN)
- Configurable failure rate threshold
- Automatic transition from OPEN to HALF_OPEN after a waiting period
- Monitors both exceptions and slow calls

### Rate Limiter
The Rate Limiter pattern limits the rate of incoming requests to a component, preventing it from being overwhelmed.

**Key characteristics:**
- Configurable number of permitted calls per time period
- Configurable timeout for threads waiting for permission
- Nanosecond precision for accurate rate limiting
- Lock-free atomic implementation

### Retry
The Retry pattern automatically retries failed operations, which is useful for handling transient failures.

**Key characteristics:**
- Configurable maximum number of retry attempts
- Support for various backoff strategies (fixed, exponential, linear, random, fibonacci)
- Ability to specify which exceptions should trigger a retry
- Ability to retry based on results (not just exceptions)

### Bulkhead
The Bulkhead pattern isolates failures in one part of a system from taking down the entire system by limiting the number of concurrent calls.

**Two implementations:**
- **Semaphore Bulkhead**: Limits concurrent execution using a semaphore
- **Thread Pool Bulkhead**: Uses a bounded queue and a fixed thread pool

**Key characteristics:**
- Configurable maximum concurrent calls
- Configurable maximum wait time (for semaphore bulkhead)
- Configurable queue capacity (for thread pool bulkhead)
- Thread isolation capabilities (for thread pool bulkhead)

## Building and Testing

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=resilience4py --cov-report=term-missing --cov-report=html

# Run specific test module
pytest tests/circuitbreaker/

# Run tests matching a pattern
pytest -k "test_circuit_breaker"

# Run tests with verbose output
pytest -v

# Run tests in parallel (requires pytest-xdist)
pytest -n auto
```

### Using Make (if Makefile is available)

```bash
# Install dependencies
make install

# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests
make test-integration

# Generate coverage report
make coverage

# Format code
make format

# Run linting
make lint

# Run type checking
make typecheck

# Clean build artifacts
make clean
```

### Test Coverage

The project currently has 44% test coverage. View the detailed coverage report by opening `htmlcov/index.html` after running tests with coverage.

### Code Quality

```bash
# Format code with black
black src/ tests/

# Run linting with flake8
flake8 src/ tests/

# Run type checking with mypy
mypy src/

# Run all quality checks
black src/ tests/ && flake8 src/ tests/ && mypy src/
```

## Project Structure

```
resilience4py/
├── src/resilience4py/
│   ├── core/               # Base classes and utilities
│   │   ├── config.py       # Base configuration classes
│   │   ├── registry.py     # Generic registry pattern
│   │   ├── events.py       # Event system infrastructure
│   │   ├── decorators.py   # Base decorator utilities
│   │   └── metrics.py      # Metrics abstractions
│   ├── circuitbreaker/     # Circuit breaker implementation
│   ├── bulkhead/           # Bulkhead pattern
│   ├── ratelimiter/        # Rate limiting
│   └── retry/              # Retry mechanism
├── tests/                  # Test suite
│   ├── core/              # Core infrastructure tests
│   ├── circuitbreaker/    # Circuit breaker tests
│   ├── bulkhead/          # Bulkhead tests
│   ├── ratelimiter/       # Rate limiter tests
│   └── retry/             # Retry tests
├── pyproject.toml         # Project configuration
├── pytest.ini             # Pytest configuration
└── README.md              # This file
```

## Development

### Setting up development environment

1. Clone the repository:
```bash
git clone https://github.com/nobelk/resilience4py.git
cd resilience4py
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
uv pip install -e ".[test]"
```

4. Run tests to ensure everything is working:
```bash
pytest
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and ensure they pass
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [resilience4j](https://github.com/resilience4j/resilience4j) - The original Java library that inspired this Python port
- The resilience4j team for their excellent documentation and design patterns

