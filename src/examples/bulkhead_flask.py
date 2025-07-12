"""
Flask API example demonstrating Bulkhead pattern.

This example shows how to use the Bulkhead pattern to isolate
different types of operations and control concurrency in a Flask application.
"""

import asyncio
import random
import time
import threading
from datetime import timedelta
from typing import Dict, Any

from flask import Flask, jsonify, request
from resilience4py.bulkhead import SemaphoreBulkhead
from resilience4py.bulkhead.config import BulkheadConfig

app = Flask(__name__)

# Configure different bulkheads for different operation types
cpu_intensive_bulkhead = SemaphoreBulkhead(
    "cpu-intensive",
    BulkheadConfig(
        max_concurrent_calls=2,  # Limit CPU-intensive operations
        max_wait_duration=timedelta(seconds=5)
    )
)

io_operations_bulkhead = SemaphoreBulkhead(
    "io-operations",
    BulkheadConfig(
        max_concurrent_calls=10,  # Allow more I/O operations
        max_wait_duration=timedelta(seconds=3)
    )
)

database_bulkhead = SemaphoreBulkhead(
    "database-operations",
    BulkheadConfig(
        max_concurrent_calls=5,  # Database connection pool size
        max_wait_duration=timedelta(seconds=2)
    )
)

# Premium users get higher concurrency
premium_bulkhead = SemaphoreBulkhead(
    "premium-operations",
    BulkheadConfig(
        max_concurrent_calls=20,
        max_wait_duration=timedelta(seconds=1)
    )
)

# Global state tracking
operation_stats = {
    "cpu_operations": {"active": 0, "completed": 0, "rejected": 0},
    "io_operations": {"active": 0, "completed": 0, "rejected": 0},
    "database_operations": {"active": 0, "completed": 0, "rejected": 0},
    "premium_operations": {"active": 0, "completed": 0, "rejected": 0}
}

def track_operation(operation_type: str, status: str):
    """Track operation statistics."""
    operation_stats[operation_type][status] += 1

def simulate_cpu_intensive_work():
    """Simulate CPU-intensive work."""
    track_operation("cpu_operations", "active")
    
    # Simulate CPU work (computing prime numbers)
    start_time = time.time()
    primes = []
    n = 10000
    
    for num in range(2, n):
        for i in range(2, int(num ** 0.5) + 1):
            if num % i == 0:
                break
        else:
            primes.append(num)
    
    execution_time = time.time() - start_time
    track_operation("cpu_operations", "completed")
    
    return {
        "operation": "cpu_intensive",
        "primes_found": len(primes),
        "execution_time_seconds": round(execution_time, 3),
        "thread_id": threading.current_thread().ident
    }

def simulate_io_operation():
    """Simulate I/O operation (file read/network call)."""
    track_operation("io_operations", "active")
    
    # Simulate I/O delay
    delay = random.uniform(0.5, 2.0)
    time.sleep(delay)
    
    track_operation("io_operations", "completed")
    
    return {
        "operation": "io_operation",
        "simulated_delay_seconds": round(delay, 3),
        "data_size_mb": random.randint(1, 100),
        "thread_id": threading.current_thread().ident
    }

def simulate_database_query():
    """Simulate database query."""
    track_operation("database_operations", "active")
    
    # Simulate database query time
    query_time = random.uniform(0.1, 1.0)
    time.sleep(query_time)
    
    # Simulate occasional database errors
    if random.random() < 0.1:
        track_operation("database_operations", "completed")
        raise Exception("Database connection timeout")
    
    track_operation("database_operations", "completed")
    
    return {
        "operation": "database_query",
        "query_time_seconds": round(query_time, 3),
        "rows_returned": random.randint(1, 1000),
        "thread_id": threading.current_thread().ident
    }

def simulate_premium_operation():
    """Simulate premium user operation."""
    track_operation("premium_operations", "active")
    
    # Premium operations are faster and more reliable
    operation_time = random.uniform(0.1, 0.5)
    time.sleep(operation_time)
    
    track_operation("premium_operations", "completed")
    
    return {
        "operation": "premium_service",
        "execution_time_seconds": round(operation_time, 3),
        "priority": "high",
        "thread_id": threading.current_thread().ident
    }

@cpu_intensive_bulkhead
def protected_cpu_operation() -> Dict[str, Any]:
    """CPU-intensive operation protected by bulkhead."""
    return simulate_cpu_intensive_work()

@io_operations_bulkhead  
def protected_io_operation() -> Dict[str, Any]:
    """I/O operation protected by bulkhead."""
    return simulate_io_operation()

@database_bulkhead
def protected_database_operation() -> Dict[str, Any]:
    """Database operation protected by bulkhead."""
    return simulate_database_query()

@premium_bulkhead
def protected_premium_operation() -> Dict[str, Any]:
    """Premium operation protected by bulkhead."""
    return simulate_premium_operation()

@app.route('/api/cpu-intensive')
def cpu_intensive_endpoint():
    """Endpoint for CPU-intensive operations."""
    start_time = time.time()
    
    try:
        result = protected_cpu_operation()
        total_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "data": result,
            "total_response_time_seconds": round(total_time, 3),
            "bulkhead": {
                "name": cpu_intensive_bulkhead.name,
                "available_concurrent_calls": cpu_intensive_bulkhead._semaphore._value,
                "max_concurrent_calls": 2
            }
        })
    
    except Exception as e:
        track_operation("cpu_operations", "rejected")
        total_time = time.time() - start_time
        
        return jsonify({
            "status": "rejected",
            "error": str(e),
            "total_response_time_seconds": round(total_time, 3),
            "bulkhead": {
                "name": cpu_intensive_bulkhead.name,
                "available_concurrent_calls": cpu_intensive_bulkhead._semaphore._value,
                "max_concurrent_calls": 2
            },
            "message": "CPU operations bulkhead is full. Please try again later."
        }), 503

@app.route('/api/io-operation')
def io_operation_endpoint():
    """Endpoint for I/O operations."""
    start_time = time.time()
    
    try:
        result = protected_io_operation()
        total_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "data": result,
            "total_response_time_seconds": round(total_time, 3),
            "bulkhead": {
                "name": io_operations_bulkhead.name,
                "available_concurrent_calls": io_operations_bulkhead._semaphore._value,
                "max_concurrent_calls": 10
            }
        })
    
    except Exception as e:
        track_operation("io_operations", "rejected")
        total_time = time.time() - start_time
        
        return jsonify({
            "status": "rejected",
            "error": str(e),
            "total_response_time_seconds": round(total_time, 3),
            "bulkhead": {
                "name": io_operations_bulkhead.name,
                "available_concurrent_calls": io_operations_bulkhead._semaphore._value,
                "max_concurrent_calls": 10
            },
            "message": "I/O operations bulkhead is full. Please try again later."
        }), 503

@app.route('/api/database')
def database_endpoint():
    """Endpoint for database operations."""
    start_time = time.time()
    
    try:
        result = protected_database_operation()
        total_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "data": result,
            "total_response_time_seconds": round(total_time, 3),
            "bulkhead": {
                "name": database_bulkhead.name,
                "available_concurrent_calls": database_bulkhead._semaphore._value,
                "max_concurrent_calls": 5
            }
        })
    
    except Exception as e:
        if "bulkhead" in str(e).lower():
            track_operation("database_operations", "rejected")
            error_type = "rejected"
            status_code = 503
        else:
            error_type = "database_error"
            status_code = 500
        
        total_time = time.time() - start_time
        
        return jsonify({
            "status": error_type,
            "error": str(e),
            "total_response_time_seconds": round(total_time, 3),
            "bulkhead": {
                "name": database_bulkhead.name,
                "available_concurrent_calls": database_bulkhead._semaphore._value,
                "max_concurrent_calls": 5
            }
        }), status_code

@app.route('/api/premium')
def premium_endpoint():
    """Endpoint for premium operations."""
    # Check if user is premium (in real app, check auth/subscription)
    is_premium = request.headers.get('X-User-Premium', 'false').lower() == 'true'
    
    if not is_premium:
        return jsonify({
            "status": "forbidden",
            "error": "Premium subscription required",
            "message": "Add 'X-User-Premium: true' header to simulate premium access"
        }), 403
    
    start_time = time.time()
    
    try:
        result = protected_premium_operation()
        total_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "data": result,
            "total_response_time_seconds": round(total_time, 3),
            "bulkhead": {
                "name": premium_bulkhead.name,
                "available_concurrent_calls": premium_bulkhead._semaphore._value,
                "max_concurrent_calls": 20
            }
        })
    
    except Exception as e:
        track_operation("premium_operations", "rejected")
        total_time = time.time() - start_time
        
        return jsonify({
            "status": "rejected",
            "error": str(e),
            "total_response_time_seconds": round(total_time, 3),
            "bulkhead": {
                "name": premium_bulkhead.name,
                "available_concurrent_calls": premium_bulkhead._semaphore._value,
                "max_concurrent_calls": 20
            }
        }), 503

@app.route('/api/bulkhead/status')
def bulkhead_status():
    """Get status of all bulkheads."""
    return jsonify({
        "bulkheads": {
            "cpu_intensive": {
                "name": cpu_intensive_bulkhead.name,
                "available_concurrent_calls": cpu_intensive_bulkhead._semaphore._value,
                "max_concurrent_calls": 2,
                "current_usage_percent": ((2 - cpu_intensive_bulkhead._semaphore._value) / 2) * 100
            },
            "io_operations": {
                "name": io_operations_bulkhead.name,
                "available_concurrent_calls": io_operations_bulkhead._semaphore._value,
                "max_concurrent_calls": 10,
                "current_usage_percent": ((10 - io_operations_bulkhead._semaphore._value) / 10) * 100
            },
            "database": {
                "name": database_bulkhead.name,
                "available_concurrent_calls": database_bulkhead._semaphore._value,
                "max_concurrent_calls": 5,
                "current_usage_percent": ((5 - database_bulkhead._semaphore._value) / 5) * 100
            },
            "premium": {
                "name": premium_bulkhead.name,
                "available_concurrent_calls": premium_bulkhead._semaphore._value,
                "max_concurrent_calls": 20,
                "current_usage_percent": ((20 - premium_bulkhead._semaphore._value) / 20) * 100
            }
        },
        "operation_statistics": operation_stats
    })

@app.route('/api/bulkhead/load-test')
def load_test():
    """Simulate concurrent load to test bulkhead behavior."""
    operation_type = request.args.get('type', 'cpu')
    concurrent_requests = int(request.args.get('requests', 5))
    
    results = []
    
    # This is a simplified load test - in a real app you'd use proper threading
    for i in range(concurrent_requests):
        try:
            if operation_type == 'cpu':
                result = protected_cpu_operation()
                results.append(f"Request {i+1}: Success")
            elif operation_type == 'io':
                result = protected_io_operation()
                results.append(f"Request {i+1}: Success")
            elif operation_type == 'database':
                result = protected_database_operation()
                results.append(f"Request {i+1}: Success")
            elif operation_type == 'premium':
                result = protected_premium_operation()
                results.append(f"Request {i+1}: Success")
        except Exception as e:
            results.append(f"Request {i+1}: Rejected - {str(e)}")
    
    return jsonify({
        "load_test_results": {
            "operation_type": operation_type,
            "concurrent_requests": concurrent_requests,
            "results": results
        },
        "current_bulkhead_status": {
            operation_type: {
                "available_calls": getattr(globals()[f"{operation_type}_intensive_bulkhead" if operation_type == "cpu" else f"{operation_type}_operations_bulkhead" if operation_type in ["io"] else f"{operation_type}_bulkhead"], "available_concurrent_calls", "N/A")
            }
        }
    })

if __name__ == '__main__':
    print("Bulkhead Pattern Flask Example")
    print("==============================")
    print("Available endpoints:")
    print("- GET  /api/cpu-intensive - CPU-intensive operations (max 2 concurrent)")
    print("- GET  /api/io-operation - I/O operations (max 10 concurrent)")
    print("- GET  /api/database - Database operations (max 5 concurrent)")
    print("- GET  /api/premium - Premium operations (max 20 concurrent)")
    print("- GET  /api/bulkhead/status - Check all bulkhead statuses")
    print("- GET  /api/bulkhead/load-test?type=X&requests=N - Load test bulkheads")
    print("\nHeaders:")
    print("- X-User-Premium: true (required for premium endpoint)")
    print("\nLoad test types:")
    print("- cpu, io, database, premium")
    print("\nTest sequence:")
    print("1. Check /api/bulkhead/status to see initial state")
    print("2. Make multiple concurrent requests to different endpoints")
    print("3. Use load test endpoint to quickly hit bulkhead limits")
    print("4. Monitor how different operation types are isolated")
    print("5. Observe that one bulkhead being full doesn't affect others")
    
    app.run(debug=True, port=5004, threaded=True)