"""
Flask API example demonstrating Rate Limiter pattern.

This example shows how to use the Rate Limiter pattern to control
the rate of requests to API endpoints in a Flask application.
"""

import time
from datetime import timedelta
from typing import Dict, Any

from flask import Flask, jsonify, request, g
from resilience4py.ratelimiter import RateLimiter
from resilience4py.ratelimiter.config import RateLimiterConfig

app = Flask(__name__)

# Configure different rate limiters for different endpoints
api_rate_limiter = RateLimiter(
    "api-general",
    RateLimiterConfig(
        limit_for_period=10,  # 10 requests
        limit_refresh_period=timedelta(seconds=60),  # per minute
        timeout_duration=timedelta(seconds=5)  # wait up to 5 seconds for permission
    )
)

premium_api_rate_limiter = RateLimiter(
    "api-premium",
    RateLimiterConfig(
        limit_for_period=100,  # 100 requests
        limit_refresh_period=timedelta(seconds=60),  # per minute
        timeout_duration=timedelta(seconds=1)  # wait up to 1 second for permission
    )
)

upload_rate_limiter = RateLimiter(
    "api-upload",
    RateLimiterConfig(
        limit_for_period=5,  # 5 uploads
        limit_refresh_period=timedelta(minutes=10),  # per 10 minutes
        timeout_duration=timedelta(seconds=0)  # no waiting, immediate rejection
    )
)

def get_user_tier():
    """Simulate user tier detection from headers or auth."""
    user_tier = request.headers.get('X-User-Tier', 'standard')
    return user_tier

def simulate_data_processing():
    """Simulate some data processing work."""
    time.sleep(0.1)  # Simulate processing time
    return {
        "processed_data": f"Result processed at {time.time()}",
        "processing_time_ms": 100
    }

@api_rate_limiter
def process_standard_request() -> Dict[str, Any]:
    """Process request with standard rate limiting."""
    return simulate_data_processing()

@premium_api_rate_limiter
def process_premium_request() -> Dict[str, Any]:
    """Process request with premium rate limiting."""
    return simulate_data_processing()

@upload_rate_limiter
def process_upload_request() -> Dict[str, Any]:
    """Process upload with strict rate limiting."""
    return {
        "upload_id": f"upload_{int(time.time())}",
        "status": "accepted",
        "timestamp": time.time()
    }

@app.route('/api/data')
def get_data():
    """General API endpoint with rate limiting based on user tier."""
    user_tier = get_user_tier()
    
    try:
        if user_tier == 'premium':
            result = process_premium_request()
            rate_limiter_name = "api-premium"
            rate_limiter = premium_api_rate_limiter
        else:
            result = process_standard_request()
            rate_limiter_name = "api-general"
            rate_limiter = api_rate_limiter
        
        return jsonify({
            "status": "success",
            "data": result,
            "user_tier": user_tier,
            "rate_limiter": rate_limiter_name,
            "available_permissions": rate_limiter.available_permissions
        })
    
    except Exception as e:
        return jsonify({
            "status": "rate_limited",
            "error": "Rate limit exceeded",
            "user_tier": user_tier,
            "retry_after_seconds": 60,
            "message": "Please try again later"
        }), 429

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload endpoint with strict rate limiting."""
    try:
        result = process_upload_request()
        
        return jsonify({
            "status": "success",
            "data": result,
            "available_permissions": upload_rate_limiter.available_permissions,
            "next_reset_in_seconds": 600  # 10 minutes
        })
    
    except Exception as e:
        return jsonify({
            "status": "rate_limited",
            "error": "Upload rate limit exceeded",
            "message": "Maximum 5 uploads per 10 minutes allowed",
            "retry_after_seconds": 600
        }), 429

@app.route('/api/rate-limits')
def get_rate_limits():
    """Get current rate limit status for all limiters."""
    user_tier = get_user_tier()
    
    rate_limiters_status = {
        "general_api": {
            "name": api_rate_limiter.name,
            "available_permissions": api_rate_limiter.available_permissions,
            "limit_for_period": 10,
            "period_seconds": 60
        },
        "premium_api": {
            "name": premium_api_rate_limiter.name,
            "available_permissions": premium_api_rate_limiter.available_permissions,
            "limit_for_period": 100,
            "period_seconds": 60
        },
        "upload_api": {
            "name": upload_rate_limiter.name,
            "available_permissions": upload_rate_limiter.available_permissions,
            "limit_for_period": 5,
            "period_seconds": 600
        }
    }
    
    return jsonify({
        "user_tier": user_tier,
        "rate_limiters": rate_limiters_status,
        "current_time": time.time()
    })

@app.route('/api/stress-test')
def stress_test():
    """Endpoint for testing rate limiting under load."""
    user_tier = get_user_tier()
    request_count = int(request.args.get('count', 1))
    
    results = []
    successful_requests = 0
    rate_limited_requests = 0
    
    for i in range(request_count):
        try:
            if user_tier == 'premium':
                result = process_premium_request()
                successful_requests += 1
                results.append(f"Request {i+1}: Success")
            else:
                result = process_standard_request()
                successful_requests += 1
                results.append(f"Request {i+1}: Success")
        except Exception:
            rate_limited_requests += 1
            results.append(f"Request {i+1}: Rate Limited")
    
    return jsonify({
        "total_requests": request_count,
        "successful_requests": successful_requests,
        "rate_limited_requests": rate_limited_requests,
        "user_tier": user_tier,
        "results": results,
        "available_permissions": (
            premium_api_rate_limiter.available_permissions 
            if user_tier == 'premium' 
            else api_rate_limiter.available_permissions
        )
    })

@app.before_request
def before_request():
    """Add request start time for tracking."""
    g.start_time = time.time()

@app.after_request
def after_request(response):
    """Add rate limiting headers to response."""
    user_tier = get_user_tier()
    
    if user_tier == 'premium':
        response.headers['X-RateLimit-Limit'] = '100'
        response.headers['X-RateLimit-Remaining'] = str(premium_api_rate_limiter.available_permissions)
    else:
        response.headers['X-RateLimit-Limit'] = '10'
        response.headers['X-RateLimit-Remaining'] = str(api_rate_limiter.available_permissions)
    
    response.headers['X-RateLimit-Reset'] = str(int(time.time()) + 60)
    
    if hasattr(g, 'start_time'):
        response.headers['X-Response-Time'] = f"{(time.time() - g.start_time) * 1000:.2f}ms"
    
    return response

if __name__ == '__main__':
    print("Rate Limiter Flask Example")
    print("==========================")
    print("Available endpoints:")
    print("- GET  /api/data - General API with tier-based rate limiting")
    print("- POST /api/upload - Upload API with strict rate limiting")
    print("- GET  /api/rate-limits - Check current rate limit status")
    print("- GET  /api/stress-test?count=N - Test rate limiting with N requests")
    print("\nHeaders:")
    print("- X-User-Tier: standard|premium (affects rate limits)")
    print("\nTest sequence:")
    print("1. Call /api/data multiple times as 'standard' user")
    print("2. Add 'X-User-Tier: premium' header and test higher limits")
    print("3. Test /api/upload endpoint (strict 5 per 10 minutes)")
    print("4. Use /api/stress-test?count=15 to quickly hit limits")
    print("5. Monitor rate limit headers in responses")
    
    app.run(debug=True, port=5002)