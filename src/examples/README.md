# resilience4py Flask Examples

This directory contains Flask API examples demonstrating how to use resilience4py patterns in real-world web applications.

## Examples Overview

| Example | Port | Pattern | Description |
|---------|------|---------|-------------|
| `circuit_breaker_flask.py` | 5001 | Circuit Breaker | Protect external API calls with automatic failure detection |
| `rate_limiter_flask.py` | 5002 | Rate Limiter | Control request rates with tier-based limiting |
| `retry_flask.py` | 5003 | Retry | Automatic retry with various backoff strategies |
| `bulkhead_flask.py` | 5004 | Bulkhead | Isolate different operation types with concurrency control |

## Prerequisites

Install Flask for running the examples:

```bash
# Using uv (recommended)
uv add flask

# Or using pip
pip install flask
```

## Running the Examples

Each example runs on a different port to allow running multiple examples simultaneously:

```bash
# Circuit Breaker example (port 5001)
python src/examples/circuit_breaker_flask.py

# Rate Limiter example (port 5002)  
python src/examples/rate_limiter_flask.py

# Retry example (port 5003)
python src/examples/retry_flask.py

# Bulkhead example (port 5004)
python src/examples/bulkhead_flask.py
```

## Example Details

### Circuit Breaker (`circuit_breaker_flask.py`)

Demonstrates how to protect external API calls from cascading failures:

- **Key endpoints:**
  - `GET /api/data` - Make protected external API call
  - `GET /api/health` - Check circuit breaker status and metrics
  - `POST /api/circuit-breaker/reset` - Manually reset circuit breaker
  - `POST /api/simulate/improve-service` - Simulate service recovery

- **Features:**
  - Automatic failure detection (50% failure rate threshold)
  - State transitions (CLOSED → OPEN → HALF_OPEN)
  - Slow call detection (>2 seconds)
  - Fallback responses when circuit is open
  - Real-time metrics monitoring

### Rate Limiter (`rate_limiter_flask.py`)

Shows how to implement tier-based rate limiting for API endpoints:

- **Key endpoints:**
  - `GET /api/data` - General API with tier-based rate limiting
  - `POST /api/upload` - Strict upload rate limiting (5 per 10 minutes)
  - `GET /api/rate-limits` - Check current rate limit status
  - `GET /api/stress-test?count=N` - Test rate limiting under load

- **Features:**
  - User tier detection (`X-User-Tier` header)
  - Different limits for standard (10/min) vs premium (100/min) users
  - Rate limit headers in responses
  - Immediate rejection vs queuing with timeout

### Retry (`retry_flask.py`)

Demonstrates various retry strategies for handling transient failures:

- **Key endpoints:**
  - `GET /api/retry/fixed?scenario=X` - Fixed interval retry
  - `GET /api/retry/exponential?scenario=X` - Exponential backoff retry
  - `GET /api/retry/fibonacci?scenario=X` - Fibonacci backoff retry
  - `GET /api/retry/database` - Database-specific retry with custom conditions
  - `GET /api/retry/metrics` - View retry statistics

- **Features:**
  - Multiple backoff strategies (fixed, exponential, fibonacci)
  - Configurable failure scenarios (transient, improving, persistent)
  - Exception-specific retry conditions
  - Detailed metrics and execution time tracking

### Bulkhead (`bulkhead_flask.py`)

Shows how to isolate different types of operations using bulkheads:

- **Key endpoints:**
  - `GET /api/cpu-intensive` - CPU-intensive operations (max 2 concurrent)
  - `GET /api/io-operation` - I/O operations (max 10 concurrent)
  - `GET /api/database` - Database operations (max 5 concurrent)
  - `GET /api/premium` - Premium operations (max 20 concurrent)
  - `GET /api/bulkhead/status` - Check all bulkhead statuses
  - `GET /api/bulkhead/load-test?type=X&requests=N` - Load test bulkheads

- **Features:**
  - Different concurrency limits for different operation types
  - Operation isolation (one bulkhead failure doesn't affect others)
  - Resource usage monitoring
  - Premium user tier with higher limits

## Testing the Examples

### Basic Testing

1. **Start an example application:**
   ```bash
   python src/examples/circuit_breaker_flask.py
   ```

2. **Test using curl or a REST client:**
   ```bash
   # Test circuit breaker
   curl http://localhost:5001/api/data
   curl http://localhost:5001/api/health
   
   # Test rate limiter with different tiers
   curl http://localhost:5002/api/data
   curl -H "X-User-Tier: premium" http://localhost:5002/api/data
   
   # Test retry with different scenarios
   curl http://localhost:5003/api/retry/exponential?scenario=improving
   curl http://localhost:5003/api/retry/metrics
   
   # Test bulkhead
   curl http://localhost:5004/api/cpu-intensive
   curl http://localhost:5004/api/bulkhead/status
   ```

### Load Testing

Use tools like Apache Bench (ab) or curl in loops to test resilience patterns under load:

```bash
# Test circuit breaker under load
for i in {1..20}; do curl http://localhost:5001/api/data & done

# Test rate limiter
for i in {1..15}; do curl http://localhost:5002/api/data && sleep 0.1; done

# Test bulkhead isolation
for i in {1..5}; do curl http://localhost:5004/api/cpu-intensive & done
for i in {1..5}; do curl http://localhost:5004/api/io-operation & done
```

### Advanced Testing Scenarios

1. **Circuit Breaker Recovery Testing:**
   - Make multiple requests to trigger circuit opening
   - Wait for half-open transition
   - Simulate service improvement
   - Observe circuit closing

2. **Rate Limiter Tier Testing:**
   - Test with standard user limits
   - Switch to premium tier
   - Compare available request quotas

3. **Retry Strategy Comparison:**
   - Test same scenario with different retry strategies
   - Compare execution times and success rates
   - Monitor retry attempt patterns

4. **Bulkhead Isolation Testing:**
   - Saturate one bulkhead completely
   - Verify other bulkheads continue working
   - Monitor resource usage across operation types

## Integration Patterns

These examples can be combined to create comprehensive resilience strategies:

```python
# Example: Combining multiple patterns
@CircuitBreaker("external-api", circuit_config)
@RateLimiter("api-calls", rate_config)  
@Retry("api-retry", retry_config)
@Bulkhead("api-bulkhead", bulkhead_config)
def robust_api_call():
    return external_service.call()
```

## Monitoring and Observability

All examples include:
- Real-time metrics endpoints
- Detailed error responses
- Performance timing information
- State transition logging
- Resource usage tracking

This makes them suitable for understanding how resilience patterns behave under different conditions and for learning how to implement monitoring in production systems.