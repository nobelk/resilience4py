#!/usr/bin/env python3
"""Example demonstrating the retry pattern from resilience4py.

Run from the repo root with the package installed editable
(``uv pip install -e .``)::

    python example_retry.py
"""

import asyncio
import random

from resilience4py.retry import (
    Retry, RetryConfig, ExponentialBackoff,
    RetryOnRetryEvent, RetryOnSuccessEvent,
)


# Example 1: Simple retry with fixed interval
def create_simple_retry():
    """Create a simple retry with default configuration."""
    config = RetryConfig(max_attempts=3)
    retry = Retry("simple-retry", config)
    
    @retry
    def flaky_function():
        """A function that randomly fails."""
        if random.random() < 0.7:  # 70% chance of failure
            print("  Function failed!")
            raise ValueError("Random failure")
        print("  Function succeeded!")
        return "Success"
    
    return flaky_function


# Example 2: Retry with exponential backoff
def create_exponential_retry():
    """Create a retry with exponential backoff."""
    config = RetryConfig(
        max_attempts=5,
        interval_function=ExponentialBackoff(
            initial_interval=0.1,
            multiplier=2.0,
            max_interval=5.0
        )
    )
    retry = Retry("exponential-retry", config)
    
    # Add event handlers
    @retry.on_retry
    def log_retry(event: RetryOnRetryEvent):
        print(f"  Retry attempt {event.attempt} scheduled after {event.wait_interval:.2f}s")
    
    @retry.on_success
    def log_success(event: RetryOnSuccessEvent):
        print(f"  Success after {event.attempt} attempts (total time: {event.total_duration:.2f}s)")
    
    @retry
    async def async_api_call():
        """Simulated async API call that may fail."""
        await asyncio.sleep(0.05)  # Simulate API latency
        if random.random() < 0.6:  # 60% chance of failure
            raise ConnectionError("API connection failed")
        return {"status": "ok", "data": "sample data"}
    
    return async_api_call


# Example 3: Retry with custom conditions
def create_conditional_retry():
    """Create a retry that only retries specific exceptions."""
    config = RetryConfig(
        max_attempts=3,
        retry_exceptions=[ConnectionError, TimeoutError],
        abort_exceptions=[ValueError],
        fail_after_max_attempts=True
    )
    retry = Retry("conditional-retry", config)
    
    @retry
    def network_operation(should_fail_with_value_error=False):
        """A function that may fail with different exceptions."""
        if should_fail_with_value_error:
            raise ValueError("This won't be retried")
        
        if random.random() < 0.5:
            raise ConnectionError("Network error - will be retried")
        
        return "Network operation successful"
    
    return network_operation


# Example 4: Retry based on result
def create_result_based_retry():
    """Create a retry that retries based on the result value."""
    def should_retry_result(result):
        """Retry if the result indicates failure."""
        return isinstance(result, dict) and result.get("status") == "error"
    
    config = RetryConfig(
        max_attempts=3,
        retry_on_result=should_retry_result
    )
    retry = Retry("result-retry", config)
    
    @retry
    def api_call_with_status():
        """Function that returns a status that might require retry."""
        if random.random() < 0.6:
            return {"status": "error", "message": "Temporary failure"}
        return {"status": "success", "data": "Important data"}
    
    return api_call_with_status


async def main():
    """Run all examples."""
    print("=== Resilience4py Retry Pattern Examples ===\n")
    
    # Example 1
    print("1. Simple retry with fixed interval:")
    flaky_func = create_simple_retry()
    try:
        result = flaky_func()
        print(f"   Result: {result}")
    except ValueError as e:
        print(f"   Failed after all retries: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Example 2
    print("2. Async retry with exponential backoff:")
    async_func = create_exponential_retry()
    try:
        result = await async_func()
        print(f"   Result: {result}")
    except ConnectionError as e:
        print(f"   Failed after all retries: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Example 3
    print("3. Conditional retry (retryable exception):")
    network_func = create_conditional_retry()
    try:
        result = network_func(should_fail_with_value_error=False)
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   Failed: {type(e).__name__}: {e}")
    
    print("\n4. Conditional retry (non-retryable exception):")
    try:
        result = network_func(should_fail_with_value_error=True)
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   Failed immediately: {type(e).__name__}: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Example 4
    print("5. Result-based retry:")
    result_func = create_result_based_retry()
    result = result_func()
    print(f"   Final result: {result}")


if __name__ == "__main__":
    # Set random seed for reproducible examples
    random.seed(42)
    asyncio.run(main())