# resilience4py

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

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
# Install editable plus test extras
uv pip install -e ".[test]"

# Or install the full dev environment (test runners + lint/type tools)
# from the lock file. Equivalent to `make install-dev`.
uv sync --dev
```

## Quick Start

```python
from datetime import timedelta

from resilience4py import (
    CircuitBreaker,
    RateLimiter,
    Retry,
    SemaphoreBulkhead,
)
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
async def rate_limited_function():
    return await expensive_operation()

# Retry example
@Retry("flaky-service", RetryConfig(
    max_attempts=3,
    wait_duration=timedelta(seconds=1)
))
async def flaky_operation():
    return await unreliable_service.call()

# Bulkhead example (Bulkhead itself is abstract — use one of its
# concrete implementations: SemaphoreBulkhead or ThreadPoolBulkhead)
@SemaphoreBulkhead("resource-pool", BulkheadConfig(
    max_concurrent_calls=10
))
async def resource_intensive_task():
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
- Atomic state updates guarded by an `asyncio.Lock`

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

## Examples

Comprehensive Flask API examples demonstrating all resilience patterns are available in the `src/examples/` directory. Each example runs as a standalone Flask application on different ports:

| Example | Port | Pattern | Description |
|---------|------|---------|-------------|
| `circuit_breaker_flask.py` | 5001 | Circuit Breaker | Protect external API calls with automatic failure detection |
| `rate_limiter_flask.py` | 5002 | Rate Limiter | Control request rates with tier-based limiting |
| `retry_flask.py` | 5003 | Retry | Automatic retry with various backoff strategies |
| `bulkhead_flask.py` | 5004 | Bulkhead | Isolate different operation types with concurrency control |

### Prerequisites

The Flask example apps live behind an optional extra so the core library
stays dependency-free. Install Flask with one of:

```bash
# Pull in resilience4py + the example deps in one shot (recommended)
uv pip install -e ".[examples]"

# Or install Flask directly
uv pip install flask
# pip equivalent:
pip install flask
```

### Running Individual Examples

Each example runs on a different port to allow running multiple examples simultaneously:

```bash
# Circuit Breaker example (port 5001)
uv run python src/examples/circuit_breaker_flask.py

# Rate Limiter example (port 5002)  
uv run python src/examples/rate_limiter_flask.py

# Retry example (port 5003)
uv run python src/examples/retry_flask.py

# Bulkhead example (port 5004)
uv run python src/examples/bulkhead_flask.py
```

### Running All Examples Simultaneously

To test pattern interactions and isolation, you can run all examples at once:

```bash
# Terminal 1: Circuit Breaker
uv run python src/examples/circuit_breaker_flask.py

# Terminal 2: Rate Limiter  
uv run python src/examples/rate_limiter_flask.py

# Terminal 3: Retry
uv run python src/examples/retry_flask.py

# Terminal 4: Bulkhead
uv run python src/examples/bulkhead_flask.py
```

### Quick Testing

Once running, test the examples with curl:

```bash
# Test Circuit Breaker
curl http://localhost:5001/api/data
curl http://localhost:5001/api/health

# Test Rate Limiter with different user tiers
curl http://localhost:5002/api/data
curl -H "X-User-Tier: premium" http://localhost:5002/api/data

# Test Retry with different strategies
curl http://localhost:5003/api/retry/exponential?scenario=improving
curl http://localhost:5003/api/retry/metrics

# Test Bulkhead with different operation types
curl http://localhost:5004/api/cpu-intensive
curl -H "X-User-Premium: true" http://localhost:5004/api/premium
curl http://localhost:5004/api/bulkhead/status
```

### Example Features

- **Interactive testing endpoints** with detailed responses
- **Real-time metrics** and status monitoring
- **Configurable failure scenarios** for testing different conditions
- **Load testing endpoints** for observing behavior under stress
- **Comprehensive documentation** with testing sequences
- **Multi-pattern demonstrations** showing how patterns work together

See [src/examples/README.md](src/examples/README.md) for detailed usage instructions and testing scenarios.

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
```

> Tip: install `pytest-xdist` separately if you want parallel execution
> (`uv pip install pytest-xdist` followed by `pytest -n auto`). It is
> intentionally not part of the default dev environment.

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
make type-check

# Clean build artifacts
make clean
```

### Test Coverage

Run `make coverage` (or `pytest --cov=resilience4py --cov-report=html`) to
generate a coverage report. The HTML report is written to `htmlcov/index.html`.

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
├── src/
│   ├── resilience4py/      # The library itself
│   │   ├── core/           # Base classes and utilities
│   │   │   ├── config.py       # Base configuration classes
│   │   │   ├── registry.py     # Generic registry pattern
│   │   │   ├── events.py       # Event system infrastructure
│   │   │   ├── decorators.py   # Base decorator utilities
│   │   │   └── metrics.py      # Metrics abstractions
│   │   ├── circuitbreaker/ # Circuit breaker implementation
│   │   ├── bulkhead/       # Bulkhead pattern
│   │   ├── ratelimiter/    # Rate limiting
│   │   └── retry/          # Retry mechanism
│   └── examples/           # Flask API examples (optional `examples` extra)
│       ├── circuit_breaker_flask.py
│       ├── rate_limiter_flask.py
│       ├── retry_flask.py
│       ├── bulkhead_flask.py
│       └── README.md
├── tests/                  # Test suite
│   ├── core/              # Core infrastructure tests
│   ├── circuitbreaker/    # Circuit breaker tests
│   ├── bulkhead/          # Bulkhead tests
│   ├── ratelimiter/       # Rate limiter tests
│   └── retry/             # Retry tests
├── pyproject.toml         # Project + pytest + coverage configuration
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

