"""
Flask API example demonstrating Retry pattern.

This example shows how to use the Retry pattern to automatically
retry failed operations with different backoff strategies.
"""

import asyncio
import random
import time
from datetime import timedelta
from typing import Dict, Any

from flask import Flask, jsonify, request
from resilience4py.retry import Retry
from resilience4py.retry.config import RetryConfig
from resilience4py.retry.interval_functions import (
    FixedInterval, ExponentialBackoff, LinearBackoff, 
    RandomInterval, FibonacciBackoff
)

app = Flask(__name__)

# Configure different retry strategies
fixed_retry = Retry(
    "fixed-retry",
    RetryConfig(
        max_attempts=3,
        wait_duration=timedelta(seconds=1),
        interval_function=FixedInterval(1.0)
    )
)

exponential_retry = Retry(
    "exponential-retry",
    RetryConfig(
        max_attempts=4,
        wait_duration=timedelta(seconds=1),
        interval_function=ExponentialBackoff(
            initial_interval=0.5,
            multiplier=2.0,
            max_interval=10.0
        )
    )
)

fibonacci_retry = Retry(
    "fibonacci-retry",
    RetryConfig(
        max_attempts=5,
        wait_duration=timedelta(seconds=1),
        interval_function=FibonacciBackoff(0.1)
    )
)

# Global state to simulate different failure scenarios
failure_scenarios = {
    "transient": {"failure_rate": 0.7, "failure_count": 0},
    "improving": {"failure_rate": 0.9, "failure_count": 0},
    "persistent": {"failure_rate": 0.95, "failure_count": 0}
}

def simulate_unreliable_service(scenario: str = "transient") -> Dict[str, Any]:
    """Simulate an unreliable service with different failure patterns."""
    scenario_config = failure_scenarios.get(scenario, failure_scenarios["transient"])
    scenario_config["failure_count"] += 1
    
    # Improving scenario: reduce failure rate over time
    if scenario == "improving":
        base_rate = 0.9
        improvement_factor = min(scenario_config["failure_count"] * 0.1, 0.8)
        current_failure_rate = max(base_rate - improvement_factor, 0.1)
    else:
        current_failure_rate = scenario_config["failure_rate"]
    
    if random.random() < current_failure_rate:
        error_types = [
            "ConnectionTimeout", 
            "ServiceUnavailable", 
            "InternalServerError",
            "NetworkError"
        ]
        raise Exception(f"{random.choice(error_types)}: Service temporarily unavailable")
    
    return {
        "data": f"Success after {scenario_config['failure_count']} attempts",
        "timestamp": time.time(),
        "scenario": scenario
    }

@fixed_retry
def call_service_with_fixed_retry(scenario: str = "transient") -> Dict[str, Any]:
    """Call service with fixed interval retry."""
    return simulate_unreliable_service(scenario)

@exponential_retry
def call_service_with_exponential_retry(scenario: str = "transient") -> Dict[str, Any]:
    """Call service with exponential backoff retry."""
    return simulate_unreliable_service(scenario)

@fibonacci_retry
def call_service_with_fibonacci_retry(scenario: str = "transient") -> Dict[str, Any]:
    """Call service with fibonacci backoff retry."""
    return simulate_unreliable_service(scenario)

# Custom retry for database operations
db_retry = Retry(
    "database-retry",
    RetryConfig(
        max_attempts=3,
        wait_duration=timedelta(seconds=2),
        interval_function=ExponentialBackoff(
            initial_interval=0.1,
            multiplier=1.5
        ),
        retry_on_exception=lambda ex: "Database" in str(ex) or "Connection" in str(ex)
    )
)

@db_retry
def simulate_database_operation() -> Dict[str, Any]:
    """Simulate database operation that might fail."""
    if random.random() < 0.6:
        error_types = ["DatabaseConnectionError", "QueryTimeoutError", "DatabaseLockError"]
        raise Exception(f"{random.choice(error_types)}: Database operation failed")
    
    return {
        "query_result": f"Database query executed at {time.time()}",
        "rows_affected": random.randint(1, 100)
    }

@app.route('/api/retry/fixed')
def test_fixed_retry():
    """Test endpoint with fixed interval retry."""
    scenario = request.args.get('scenario', 'transient')
    start_time = time.time()
    
    try:
        result = call_service_with_fixed_retry(scenario)
        execution_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "data": result,
            "retry_strategy": "fixed_interval",
            "execution_time_seconds": round(execution_time, 2),
            "retry_attempts": fixed_retry.metrics.number_of_failed_calls_without_retry_attempt + 1
        })
    
    except Exception as e:
        execution_time = time.time() - start_time
        return jsonify({
            "status": "failed",
            "error": str(e),
            "retry_strategy": "fixed_interval",
            "execution_time_seconds": round(execution_time, 2),
            "retry_attempts": fixed_retry.metrics.number_of_failed_calls_without_retry_attempt + 1,
            "max_attempts_reached": True
        }), 503

@app.route('/api/retry/exponential')
def test_exponential_retry():
    """Test endpoint with exponential backoff retry."""
    scenario = request.args.get('scenario', 'transient')
    start_time = time.time()
    
    try:
        result = call_service_with_exponential_retry(scenario)
        execution_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "data": result,
            "retry_strategy": "exponential_backoff",
            "execution_time_seconds": round(execution_time, 2),
            "retry_attempts": exponential_retry.metrics.number_of_failed_calls_without_retry_attempt + 1
        })
    
    except Exception as e:
        execution_time = time.time() - start_time
        return jsonify({
            "status": "failed",
            "error": str(e),
            "retry_strategy": "exponential_backoff",
            "execution_time_seconds": round(execution_time, 2),
            "retry_attempts": exponential_retry.metrics.number_of_failed_calls_without_retry_attempt + 1,
            "max_attempts_reached": True
        }), 503

@app.route('/api/retry/fibonacci')
def test_fibonacci_retry():
    """Test endpoint with fibonacci backoff retry."""
    scenario = request.args.get('scenario', 'transient')
    start_time = time.time()
    
    try:
        result = call_service_with_fibonacci_retry(scenario)
        execution_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "data": result,
            "retry_strategy": "fibonacci_backoff",
            "execution_time_seconds": round(execution_time, 2),
            "retry_attempts": fibonacci_retry.metrics.number_of_failed_calls_without_retry_attempt + 1
        })
    
    except Exception as e:
        execution_time = time.time() - start_time
        return jsonify({
            "status": "failed",
            "error": str(e),
            "retry_strategy": "fibonacci_backoff",
            "execution_time_seconds": round(execution_time, 2),
            "retry_attempts": fibonacci_retry.metrics.number_of_failed_calls_without_retry_attempt + 1,
            "max_attempts_reached": True
        }), 503

@app.route('/api/retry/database')
def test_database_retry():
    """Test database operation with retry."""
    start_time = time.time()
    
    try:
        result = simulate_database_operation()
        execution_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "data": result,
            "retry_strategy": "database_specific",
            "execution_time_seconds": round(execution_time, 2),
            "retry_attempts": db_retry.metrics.number_of_failed_calls_without_retry_attempt + 1
        })
    
    except Exception as e:
        execution_time = time.time() - start_time
        return jsonify({
            "status": "failed",
            "error": str(e),
            "retry_strategy": "database_specific",
            "execution_time_seconds": round(execution_time, 2),
            "retry_attempts": db_retry.metrics.number_of_failed_calls_without_retry_attempt + 1,
            "max_attempts_reached": True
        }), 503

@app.route('/api/retry/metrics')
def get_retry_metrics():
    """Get metrics for all retry instances."""
    return jsonify({
        "retry_metrics": {
            "fixed_retry": {
                "name": fixed_retry.name,
                "successful_calls_with_retry_attempt": fixed_retry.metrics.number_of_successful_calls_with_retry_attempt,
                "successful_calls_without_retry_attempt": fixed_retry.metrics.number_of_successful_calls_without_retry_attempt,
                "failed_calls_with_retry_attempt": fixed_retry.metrics.number_of_failed_calls_with_retry_attempt,
                "failed_calls_without_retry_attempt": fixed_retry.metrics.number_of_failed_calls_without_retry_attempt
            },
            "exponential_retry": {
                "name": exponential_retry.name,
                "successful_calls_with_retry_attempt": exponential_retry.metrics.number_of_successful_calls_with_retry_attempt,
                "successful_calls_without_retry_attempt": exponential_retry.metrics.number_of_successful_calls_without_retry_attempt,
                "failed_calls_with_retry_attempt": exponential_retry.metrics.number_of_failed_calls_with_retry_attempt,
                "failed_calls_without_retry_attempt": exponential_retry.metrics.number_of_failed_calls_without_retry_attempt
            },
            "fibonacci_retry": {
                "name": fibonacci_retry.name,
                "successful_calls_with_retry_attempt": fibonacci_retry.metrics.number_of_successful_calls_with_retry_attempt,
                "successful_calls_without_retry_attempt": fibonacci_retry.metrics.number_of_successful_calls_without_retry_attempt,
                "failed_calls_with_retry_attempt": fibonacci_retry.metrics.number_of_failed_calls_with_retry_attempt,
                "failed_calls_without_retry_attempt": fibonacci_retry.metrics.number_of_failed_calls_without_retry_attempt
            },
            "database_retry": {
                "name": db_retry.name,
                "successful_calls_with_retry_attempt": db_retry.metrics.number_of_successful_calls_with_retry_attempt,
                "successful_calls_without_retry_attempt": db_retry.metrics.number_of_successful_calls_without_retry_attempt,
                "failed_calls_with_retry_attempt": db_retry.metrics.number_of_failed_calls_with_retry_attempt,
                "failed_calls_without_retry_attempt": db_retry.metrics.number_of_failed_calls_without_retry_attempt
            }
        }
    })

@app.route('/api/retry/reset-scenarios', methods=['POST'])
def reset_scenarios():
    """Reset failure scenario counters."""
    for scenario in failure_scenarios:
        failure_scenarios[scenario]["failure_count"] = 0
    
    return jsonify({
        "message": "All failure scenario counters reset",
        "scenarios": list(failure_scenarios.keys())
    })

if __name__ == '__main__':
    print("Retry Pattern Flask Example")
    print("===========================")
    print("Available endpoints:")
    print("- GET  /api/retry/fixed?scenario=X - Test fixed interval retry")
    print("- GET  /api/retry/exponential?scenario=X - Test exponential backoff retry")
    print("- GET  /api/retry/fibonacci?scenario=X - Test fibonacci backoff retry")
    print("- GET  /api/retry/database - Test database-specific retry")
    print("- GET  /api/retry/metrics - View retry metrics")
    print("- POST /api/retry/reset-scenarios - Reset failure counters")
    print("\nFailure scenarios:")
    print("- transient: 70% failure rate (default)")
    print("- improving: Starts at 90% failure, improves with each call")
    print("- persistent: 95% failure rate (most likely to exhaust retries)")
    print("\nTest sequence:")
    print("1. Test different retry strategies with various scenarios")
    print("2. Compare execution times and success rates")
    print("3. Monitor metrics to see retry patterns")
    print("4. Reset scenarios to test multiple times")
    
    app.run(debug=True, port=5003)