"""Regression tests for issues fixed during the improvement pass.

Each test below pins behavior that was either broken or under-specified.
The references in the test docstrings point to the corresponding entry in
``improvements.md`` so future readers can connect the test to the rationale.
"""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest

from resilience4py.bulkhead.config import BulkheadConfig, ThreadPoolBulkheadConfig
from resilience4py.bulkhead.semaphore_bulkhead import SemaphoreBulkhead
from resilience4py.bulkhead.threadpool_bulkhead import ThreadPoolBulkhead
from resilience4py.circuitbreaker.circuit_breaker import CircuitBreaker
from resilience4py.ratelimiter.atomic_rate_limiter import AtomicRateLimiter
from resilience4py.ratelimiter.config import RateLimiterConfig
from resilience4py.ratelimiter.events import (
    RateLimiterOnFailureEvent,
    RateLimiterOnSuccessEvent,
)
from resilience4py.ratelimiter.rate_limiter import RateLimiter


class TestSyncDecoratorKwargsBug:
    """Improvements doc 1.2 — sync decorators must accept keyword arguments.

    Previously, ``loop.run_in_executor(None, func, *args, **kwargs)`` raised
    TypeError because ``run_in_executor`` does not accept kwargs. The fix
    binds kwargs with ``functools.partial`` before submission.
    """

    def test_circuit_breaker_sync_with_kwargs(self):
        cb = CircuitBreaker("regression-cb-sync-kwargs")

        @cb
        def add(a, b=0, c=0):
            return a + b + c

        assert add(1, b=2, c=3) == 6

    def test_circuit_breaker_sync_with_only_kwargs(self):
        cb = CircuitBreaker("regression-cb-only-kwargs")

        @cb
        def greet(*, name):
            return f"hello {name}"

        assert greet(name="world") == "hello world"

    @pytest.mark.asyncio
    async def test_circuit_breaker_async_path_invokes_sync_func_with_kwargs(self):
        """Sync function executed via the async _execute_async path."""
        cb = CircuitBreaker("regression-cb-exec-async")

        def add(a, b=0):
            return a + b

        result = await cb._execute_async(add, 1, b=41)
        assert result == 42

    @pytest.mark.asyncio
    async def test_semaphore_bulkhead_sync_func_with_kwargs(self):
        bh = SemaphoreBulkhead(
            "regression-bh-sync-kwargs",
            BulkheadConfig(max_concurrent_calls=2, max_wait_duration=timedelta(seconds=1)),
        )

        def add(a, b=0):
            return a + b

        assert await bh._execute_async(add, 1, b=41) == 42


class TestRateLimiterValidation:
    """Improvements doc 1.5 — validation must use ValueError, not assert.

    Asserts are stripped under ``python -O``, which would silently disable
    runtime validation in production builds.
    """

    def test_negative_limit_raises_value_error(self):
        with pytest.raises(ValueError, match="limit_for_period"):
            RateLimiterConfig(limit_for_period=-1)

    def test_zero_refresh_period_raises_value_error(self):
        with pytest.raises(ValueError, match="limit_refresh_period"):
            RateLimiterConfig(limit_refresh_period=timedelta(seconds=0))

    def test_negative_timeout_raises_value_error(self):
        with pytest.raises(ValueError, match="timeout_duration"):
            RateLimiterConfig(timeout_duration=timedelta(seconds=-1))


class TestMonotonicClocks:
    """Improvements doc 1.4 — timing-sensitive logic uses monotonic clocks.

    Wall-clock jumps from NTP/VM suspends would otherwise corrupt circuit
    breaker transitions and rate-limiter cycle accounting.
    """

    def test_atomic_rate_limiter_uses_monotonic_ns(self):
        """Verify time.monotonic_ns is the clock source for cycle accounting."""
        config = RateLimiterConfig(limit_for_period=2, limit_refresh_period=timedelta(seconds=1))
        limiter = AtomicRateLimiter("regression-monotonic-ns", config)

        async def run():
            with patch("time.monotonic_ns") as mock_clock:
                mock_clock.return_value = 5_000_000_000  # cycle 5
                await limiter._reserve_permission()
                assert limiter._state.active_cycle == 5
                # If implementation called time.time_ns instead, the cycle
                # would have come from the wall clock and would not equal 5.

        asyncio.run(run())

    @pytest.mark.asyncio
    async def test_circuit_breaker_uses_monotonic_for_duration(self):
        """Patching time.monotonic affects duration measurement, proving the source.

        ``time.monotonic`` is consulted both to bracket the call duration
        and to timestamp the recorded outcome, so the patch needs to
        return values for every consult, not just two.
        """
        cb = CircuitBreaker("regression-cb-monotonic")

        async def fast():
            return "ok"

        # 10.0 -> start, 10.5 -> end (=> 500ms duration), 10.5 -> outcome
        # timestamp recorded into the sliding window. Any extra trailing
        # 10.5 values are harmless filler.
        with patch("time.monotonic", side_effect=[10.0, 10.5, 10.5, 10.5]):
            await cb._execute_async(fast)

        snapshot = await cb.metrics.get_snapshot()
        assert snapshot.average_duration == pytest.approx(500.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_circuit_breaker_metrics_window_uses_monotonic(self):
        """Time-based window cleanup must use monotonic, not wall clock."""
        from resilience4py.circuitbreaker.metrics import SlidingWindowMetrics

        # Window of 10s. Record a call "now"; advance monotonic past the
        # window and confirm the entry is evicted on the next snapshot.
        with patch("time.monotonic", return_value=1000.0):
            window = SlidingWindowMetrics(
                window_size=10,
                window_type="TIME_BASED",
                slow_call_duration_threshold_ms=100.0,
            )
            await window.record_success(5.0)
            assert len(window._calls) == 1

        with patch("time.monotonic", return_value=1100.0):
            snapshot = await window.get_snapshot()
            assert snapshot.total_calls == 0


class TestConstructorNoLoopRequired:
    """Improvements doc 2.2 — constructors must not depend on a running loop.

    The old ThreadPoolBulkhead.__init__ called asyncio.create_task() and
    produced "coroutine was never awaited" warnings whenever no loop was
    running.
    """

    def test_threadpool_bulkhead_constructable_without_loop(self):
        """Should construct cleanly with no event loop, no warnings."""
        import warnings

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            bh = ThreadPoolBulkhead(
                "regression-no-loop",
                ThreadPoolBulkheadConfig(max_thread_pool_size=2, queue_capacity=1),
            )
            assert bh._metrics_initialized is False

        unwanted = [
            w for w in captured
            if issubclass(w.category, RuntimeWarning)
            and "never awaited" in str(w.message)
        ]
        assert unwanted == [], f"unexpected coroutine warnings: {unwanted}"

    def test_semaphore_bulkhead_constructable_without_loop(self):
        import warnings

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            bh = SemaphoreBulkhead(
                "regression-sem-no-loop",
                BulkheadConfig(max_concurrent_calls=3),
            )
            assert bh._metrics_initialized is False

        unwanted = [
            w for w in captured
            if issubclass(w.category, RuntimeWarning)
            and "never awaited" in str(w.message)
        ]
        assert unwanted == []


class TestNoPrivateAsyncioAccess:
    """Improvements doc 2.3 — no reads of asyncio.Semaphore._value.

    The bulkheads track available permits via an explicit counter so the
    code is portable across CPython versions and alternative event loops.
    """

    @pytest.mark.asyncio
    async def test_threadpool_uses_explicit_counter(self):
        bh = ThreadPoolBulkhead(
            "regression-no-private",
            ThreadPoolBulkheadConfig(max_thread_pool_size=2, queue_capacity=1),
        )
        assert bh._available_permits == 3
        assert await bh.acquire_permission() is True
        assert bh._available_permits == 2
        await bh.release_permission()
        assert bh._available_permits == 3

    @pytest.mark.asyncio
    async def test_semaphore_uses_explicit_counter(self):
        bh = SemaphoreBulkhead(
            "regression-sem-no-private",
            BulkheadConfig(max_concurrent_calls=2, max_wait_duration=timedelta(seconds=0)),
        )
        assert bh._available_permits == 2
        assert await bh.acquire_permission() is True
        assert bh._available_permits == 1
        assert await bh.acquire_permission() is True
        assert bh._available_permits == 0
        # Capacity exhausted — must reject.
        assert await bh.acquire_permission() is False
        await bh.release_permission()
        assert bh._available_permits == 1


class TestRateLimiterAddEventListener:
    """Improvements doc 1.6 — RateLimiter.add_event_listener must actually work."""

    @pytest.mark.asyncio
    async def test_listener_receives_success_events(self):
        received: list[Any] = []

        limiter = RateLimiter(
            "regression-listener-success",
            RateLimiterConfig(limit_for_period=5, limit_refresh_period=timedelta(seconds=1)),
        )
        limiter.add_event_listener(RateLimiterOnSuccessEvent, received.append)

        @limiter
        async def work():
            return "ok"

        await work()
        assert len(received) == 1
        assert isinstance(received[0], RateLimiterOnSuccessEvent)

    @pytest.mark.asyncio
    async def test_listener_receives_failure_events(self):
        received: list[Any] = []
        limiter = RateLimiter(
            "regression-listener-failure",
            RateLimiterConfig(
                limit_for_period=1,
                limit_refresh_period=timedelta(seconds=10),
                timeout_duration=timedelta(seconds=0),
            ),
        )
        limiter.add_event_listener(RateLimiterOnFailureEvent, received.append)

        @limiter
        async def work():
            return "ok"

        await work()  # consume the only permission
        with pytest.raises(Exception):
            await work()  # expect rejection
        assert len(received) == 1
        assert isinstance(received[0], RateLimiterOnFailureEvent)

    @pytest.mark.asyncio
    async def test_listener_added_after_first_use(self):
        """Listeners added after the underlying limiter exists still attach."""
        received: list[Any] = []
        limiter = RateLimiter(
            "regression-listener-late",
            RateLimiterConfig(limit_for_period=5, limit_refresh_period=timedelta(seconds=1)),
        )

        @limiter
        async def work():
            return "ok"

        await work()  # creates the AtomicRateLimiter
        limiter.add_event_listener(RateLimiterOnSuccessEvent, received.append)
        await work()
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_remove_event_listener(self):
        received: list[Any] = []
        limiter = RateLimiter(
            "regression-listener-remove",
            RateLimiterConfig(limit_for_period=10, limit_refresh_period=timedelta(seconds=1)),
        )
        limiter.add_event_listener(RateLimiterOnSuccessEvent, received.append)

        @limiter
        async def work():
            return "ok"

        await work()
        removed = limiter.remove_event_listener(RateLimiterOnSuccessEvent, received.append)
        assert removed is True
        await work()
        # Only one event observed — the post-removal call did not fire.
        assert len(received) == 1
