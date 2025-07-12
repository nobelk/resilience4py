"""
Flask API example demonstrating Circuit Breaker pattern.

This example shows how to use the Circuit Breaker pattern to protect
external API calls in a Flask application.
"""

import asyncio
import random
import time
from datetime import timedelta
from typing import Dict, Any

from flask import Flask, jsonify, request
from resilience4py.circuitbreaker import CircuitBreaker
from resilience4py.circuitbreaker.config import CircuitBreakerConfig

app = Flask(__name__)

# Configure Circuit Breaker for external API calls
api_circuit_breaker = CircuitBreaker(
    "external-api", 
    CircuitBreakerConfig(
        failure_rate_threshold=50.0,  # Trip when 50% of calls fail
        sliding_window_size=10,       # Consider last 10 calls
        minimum_number_of_calls=5,    # Need at least 5 calls before evaluating
        wait_duration_in_open_state=timedelta(seconds=30),  # Wait 30s before trying again
        permitted_calls_in_half_open=3,  # Allow 3 test calls in half-open
        slow_call_duration_threshold=timedelta(seconds=2),  # Calls taking >2s are slow
        slow_call_rate_threshold=100.0  # Trip when 100% of calls are slow
    )
)

# Simulate external service responses
def simulate_external_api_failure():
    """Simulate an unreliable external API that fails randomly."""
    failure_chance = 0.6  # 60% failure rate initially
    
    # Simulate slow response
    if random.random() < 0.3:
        time.sleep(3)  # 3 second delay (exceeds slow call threshold)
    
    if random.random() < failure_chance:
        raise Exception("External API is down")
    
    return {"data": "success", "timestamp": time.time()}

@api_circuit_breaker
def call_external_api() -> Dict[str, Any]:
    """Protected call to external API with Circuit Breaker."""
    return simulate_external_api_failure()

@app.route('/api/data')
def get_data():
    """Endpoint that calls external API with Circuit Breaker protection."""
    try:
        result = call_external_api()
        return jsonify({
            "status": "success",
            "data": result,
            "circuit_breaker_state": api_circuit_breaker.state.name
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "circuit_breaker_state": api_circuit_breaker.state.name,
            "fallback_data": {
                "message": "Using cached or default data due to service unavailability",
                "timestamp": time.time()
            }
        }), 503

@app.route('/api/health')
def health_check():
    """Health check endpoint showing Circuit Breaker status."""
    metrics = api_circuit_breaker.metrics
    return jsonify({
        "circuit_breaker": {
            "name": api_circuit_breaker.name,
            "state": api_circuit_breaker.state.name,
            "metrics": {
                "failure_rate": metrics.failure_rate,
                "slow_call_rate": metrics.slow_call_rate,
                "number_of_buffered_calls": metrics.number_of_buffered_calls,
                "number_of_failed_calls": metrics.number_of_failed_calls,
                "number_of_slow_calls": metrics.number_of_slow_calls,
                "number_of_successful_calls": metrics.number_of_successful_calls
            }
        }
    })

@app.route('/api/circuit-breaker/reset', methods=['POST'])
def reset_circuit_breaker():
    """Manually reset the circuit breaker to CLOSED state."""
    api_circuit_breaker.transition_to_closed_state()
    return jsonify({
        "message": "Circuit breaker reset to CLOSED state",
        "state": api_circuit_breaker.state.name
    })

@app.route('/api/simulate/improve-service', methods=['POST'])
def improve_service():
    """Simulate service improvement by reducing failure rate."""
    global simulate_external_api_failure
    
    def improved_api():
        # Much lower failure rate
        if random.random() < 0.1:  # 10% failure rate
            raise Exception("Occasional external API error")
        return {"data": "success", "timestamp": time.time()}
    
    simulate_external_api_failure = improved_api
    return jsonify({"message": "External service improved - failure rate reduced to 10%"})

if __name__ == '__main__':
    print("Circuit Breaker Flask Example")
    print("=============================")
    print("Available endpoints:")
    print("- GET  /api/data - Call external API with circuit breaker protection")
    print("- GET  /api/health - Check circuit breaker status and metrics")
    print("- POST /api/circuit-breaker/reset - Reset circuit breaker")
    print("- POST /api/simulate/improve-service - Simulate service improvement")
    print("\nTest sequence:")
    print("1. Call /api/data multiple times to see circuit breaker in action")
    print("2. Monitor /api/health to see metrics and state changes")
    print("3. Use /api/simulate/improve-service to improve the service")
    print("4. Continue calling /api/data to see recovery")
    
    app.run(debug=True, port=5001)