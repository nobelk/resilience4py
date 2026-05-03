# resilience4j Compatibility Matrix

This document records, per pattern, where `resilience4py` matches the Java
[resilience4j](https://github.com/resilience4j/resilience4j) library and
where it intentionally (or unintentionally) diverges. Use it to decide
whether the port is a faithful drop-in for your existing resilience4j
mental model.

Reference: based on the Python sources in `src/resilience4py/` and on
public resilience4j documentation. Java versions referenced are the
2.x series.

## How to read this document

For each pattern there are five fixed sections:

- **API mapping** — class / decorator / method names on each side.
- **Threading & concurrency model** — what synchronization primitives are
  used, what runs sync vs async, what the `@decorator` does to your
  function.
- **Configuration defaults** — side-by-side defaults; values in **bold**
  are deviations from resilience4j.
- **Event semantics** — emitted event types and how listeners are
  invoked.
- **Known deviations** — behavioral differences worth flagging.

A summary of cross-cutting deviations (registries, event surface,
patterns not ported) is at the bottom.

---

## Circuit Breaker

### API mapping

| Concept | resilience4j (Java) | resilience4py |
|---|---|---|
| Main class | `CircuitBreaker` | `resilience4py.circuitbreaker.CircuitBreaker` |
| Config | `CircuitBreakerConfig` (builder) | `CircuitBreakerConfig` (frozen `dataclass`) |
| Construction | `CircuitBreaker.of(name, config)` / `CircuitBreakerRegistry.circuitBreaker(name)` | `CircuitBreaker(name, config)` or `await CircuitBreaker.get_or_create(name, config)` |
| Decoration | `CircuitBreaker.decorateSupplier(cb, supplier)` etc. | `@cb` or `cb.decorate(func)` (works on sync and async) |
| Manual call | `cb.acquirePermission()` + `cb.onSuccess()` / `cb.onError()` | `await cb._state.acquire_permission()` (no public manual-call surface) |
| Rejection exception | `CallNotPermittedException` | `CallNotPermittedException` |
| Metrics snapshot | `cb.getMetrics()` | `await cb.get_metrics()` (returns `dict`) |
| Manual transitions | `cb.transitionToOpenState()`, `transitionToClosedState()`, `transitionToHalfOpenState()`, `transitionToDisabledState()`, `transitionToForcedOpenState()`, `transitionToMetricsOnlyState()` | `await cb.force_open()`, `await cb.close()`, `await cb.disable()`, `await cb.transition_to_metrics_only()`, `await cb.transition_to_state(state)` |
| Reset | `cb.reset()` | `await cb.reset()` |

### Threading & concurrency model

- **Java**: lock-free state transitions using `AtomicReference` and
  per-state metric counters via `LongAdder`. Decorators are pure — they
  return a wrapped callable that synchronously checks state.
- **Python**: state transitions are serialized through `asyncio.Lock`
  (`_state_lock`). Metrics are async-locked. The decorator returns an
  `async` wrapper for coroutine functions and a *sync* wrapper for
  ordinary functions; the sync wrapper drives the async core via
  `loop.run_until_complete` (creating a new loop) or
  `asyncio.run_coroutine_threadsafe` when called from inside a running
  loop. Sync functions passed to the async core are executed in
  `loop.run_in_executor(None, partial(func, *args, **kwargs))`.

### Configuration defaults

| Field (Python) | Java default | Python default | Notes |
|---|---|---|---|
| `failure_rate_threshold` | 50.0 | 50.0 | match |
| `slow_call_rate_threshold` | 100.0 | 100.0 | match |
| `slow_call_duration_threshold` | 60s | 60s | match |
| `permitted_calls_in_half_open` | 10 | 10 | match |
| `sliding_window_size` | 100 | 100 | match |
| `sliding_window_type` | `COUNT_BASED` | `COUNT_BASED` | match |
| `minimum_number_of_calls` | 100 | 100 | match |
| `wait_duration_in_open_state` | 60s | 60s | match |
| `max_wait_duration_in_half_open` | 0 (no limit) | 0 (no limit) | match |
| `automatic_transition_from_open_to_half_open` | `false` | **`True`** | **deviation** — Python auto-transitions on the next call after the wait window |
| `record_exceptions` | `[]` | `[]` | match |
| `ignore_exceptions` | `[]` | `[]` | match |

### Event semantics

| Java event | Python event | Emitted on |
|---|---|---|
| `CircuitBreakerOnSuccessEvent` | `CircuitBreakerOnSuccessEvent` | successful call |
| `CircuitBreakerOnErrorEvent` | `CircuitBreakerOnErrorEvent` | recorded failure |
| `CircuitBreakerOnIgnoredErrorEvent` | `CircuitBreakerOnIgnoredErrorEvent` | exception matched `ignore_exceptions` |
| `CircuitBreakerOnCallNotPermittedEvent` | `CircuitBreakerOnCallNotPermittedEvent` | call rejected by OPEN/FORCED_OPEN |
| `CircuitBreakerOnStateTransitionEvent` | `CircuitBreakerOnStateTransitionEvent` | any state change |
| `CircuitBreakerOnResetEvent` | `CircuitBreakerOnResetEvent` | `reset()` called |
| `CircuitBreakerOnFailureRateExceededEvent` | `CircuitBreakerOnFailureRateExceededEvent` | failure-rate threshold crossed |
| `CircuitBreakerOnSlowCallRateExceededEvent` | `CircuitBreakerOnSlowCallRateExceededEvent` | slow-call rate threshold crossed |
| `CircuitBreakerOnManualStateTransitionEvent` | declared (`CircuitBreakerOnManualStateTransitionEvent`) but **never emitted** | — |

Listener registration: `cb.on_event(EventClass, listener)`. Listeners are
invoked **inline** during the call path (sync listeners called directly,
async listeners awaited). Listener exceptions are silently swallowed.

### Known deviations

- `automatic_transition_from_open_to_half_open` defaults to `True` (Java:
  `false`). Effect: Python tries to leave OPEN on the next call after the
  wait window without you opting in.
- `transition_to_state()` always emits `OnStateTransitionEvent`, including
  for manual transitions. The dedicated `OnManualStateTransitionEvent`
  type exists but is unused.
- Thresholds are evaluated only after `on_success`/`on_error` records the
  call; Java additionally re-evaluates inside `acquirePermission`.
- The Python sync wrapper creates a new event loop per call when no loop
  is running; this adds latency and is not safe inside notebooks or web
  servers that already manage a loop. See the open issue tracked in
  `improvements.md` §1.3 / §2.1.

---

## Bulkhead

### API mapping

| Concept | resilience4j (Java) | resilience4py |
|---|---|---|
| Abstract base | `Bulkhead` | `resilience4py.bulkhead.Bulkhead` (abstract) |
| Semaphore variant | `SemaphoreBulkhead` | `SemaphoreBulkhead` |
| Thread-pool variant | `FixedThreadPoolBulkhead` | `ThreadPoolBulkhead` |
| Configs | `BulkheadConfig`, `ThreadPoolBulkheadConfig` | `BulkheadConfig`, `ThreadPoolBulkheadConfig` |
| Construction | `Bulkhead.of(name, config)` / registry factory | `SemaphoreBulkhead(name, config)` / `ThreadPoolBulkhead(name, config)` |
| Decoration | `Bulkhead.decorateSupplier(...)`, etc. | `@bulkhead` (works on sync and async) |
| Manual submit (thread pool) | `bulkhead.submit(callable)` returns `CompletionStage<T>` | `await bulkhead.submit(func, *args, **kwargs)` returns the awaited result directly |
| Rejection exception | `BulkheadFullException` | `BulkheadFullException` |
| Shutdown (thread pool) | `bulkhead.close()` (`AutoCloseable`) | `bulkhead.shutdown(wait=True)` |

There is **no** Python `BulkheadRegistry` — instances must be created
directly. (Java's `BulkheadRegistry` provides shared event consumers and
named lookup; the Python port omits both.)

### Threading & concurrency model

- **Java SemaphoreBulkhead**: blocking `java.util.concurrent.Semaphore`
  with timed `tryAcquire`. The decorated callable runs on the calling
  thread.
- **Python SemaphoreBulkhead**: `asyncio.Semaphore` plus an explicit
  permit counter (`_available_permits`) guarded by `_counter_lock` to
  avoid reading the private `Semaphore._value`. Sync callables passed
  to the async core are executed in
  `loop.run_in_executor(None, partial(func, *args, **kwargs))`.
- **Java FixedThreadPoolBulkhead**: bounded `LinkedBlockingQueue` plus
  `ThreadPoolExecutor`. `submit` returns a `CompletionStage`.
- **Python ThreadPoolBulkhead**: `concurrent.futures.ThreadPoolExecutor`
  with a single asyncio `Semaphore` sized to
  `max_thread_pool_size + queue_capacity` to gate both pool slots and
  queue slots together. `submit()` propagates `contextvars`,
  awaits the future, and returns its result.

### Configuration defaults

`BulkheadConfig` (semaphore variant):

| Field (Python) | Java default | Python default | Notes |
|---|---|---|---|
| `max_concurrent_calls` | 25 | 25 | match |
| `max_wait_duration` | 0ms | 0s | match (zero = non-blocking try-acquire) |

`ThreadPoolBulkheadConfig`:

| Field (Python) | Java default | Python default | Notes |
|---|---|---|---|
| `max_thread_pool_size` | `Runtime.getRuntime().availableProcessors()` | **4 (constant)** | **deviation** — Python ignores host CPU count |
| `core_thread_pool_size` | `availableProcessors() - 1` | **2 (constant)** | **deviation** — same reason |
| `queue_capacity` | 100 | 100 | match |
| `keep_alive_duration` | 20ms | 20ms | match |

### Event semantics

| Java event | Python event | Emitted on |
|---|---|---|
| `BulkheadOnCallPermittedEvent` | `BulkheadOnCallPermittedEvent` | permission acquired |
| `BulkheadOnCallRejectedEvent` | `BulkheadOnCallRejectedEvent` | bulkhead full |
| `BulkheadOnCallFinishedEvent` | `BulkheadOnCallFinishedEvent` | call completed (success or failure) |

Listener registration: `bulkhead.on_event(handler)` — note this takes
a single handler that receives **every** event type, not a per-type
filter as in Java. Handlers run inline; exceptions are silently
swallowed.

### Known deviations

- `ThreadPoolBulkhead.submit()` returns the awaited value; Java returns
  `CompletionStage<T>`. There is no fire-and-forget submit.
- `core_thread_pool_size` is not used by the Python implementation — the
  underlying `ThreadPoolExecutor` honors `max_workers` only, so the
  field is effectively decorative until consumed.
- Sizing constants (`max_thread_pool_size=4`, `core_thread_pool_size=2`)
  are independent of host CPU count.
- No `BulkheadRegistry`: instances must be tracked by the application.
- `core_thread_pool_size` validation requires it to be **strictly**
  positive; Java permits 0.

---

## Rate Limiter

### API mapping

| Concept | resilience4j (Java) | resilience4py |
|---|---|---|
| Main class | `RateLimiter` (interface), `AtomicRateLimiter` | `resilience4py.ratelimiter.RateLimiter` (high-level), `AtomicRateLimiter` (core) |
| Config | `RateLimiterConfig` (builder) | `RateLimiterConfig` (frozen dataclass) |
| Construction | `RateLimiter.of(name, config)` / `RateLimiterRegistry.rateLimiter(name)` | `RateLimiter(name, config)`; underlying limiter is created lazily on first use |
| Decoration | `RateLimiter.decorateSupplier(...)` etc. | `@RateLimiter("name", config)` (works on sync and async) |
| Manual acquire | `rl.acquirePermission()` (boolean) | `await rl.acquire_permission()` |
| Rejection exception | `RequestNotPermitted` | `RequestNotPermitted` |
| Convenience | `RateLimiter.ofDefaults(name)` | `rate_limit(limit_for_period, refresh_period_seconds)` |

### Threading & concurrency model

- **Java AtomicRateLimiter**: truly lock-free. State is an immutable
  `State` record published via `AtomicReference.compareAndSet`; the
  reservation loop retries on contention.
- **Python AtomicRateLimiter**: not lock-free despite the name. State
  transitions are serialized through `asyncio.Lock` (`_state_lock`).
  "Atomic" in this port means each reservation is a single all-or-nothing
  state update under the lock — not lock-free CAS. Wall-clock-jump
  resilience is provided by `time.monotonic_ns()`.

### Configuration defaults

| Field (Python) | Java default | Python default | Notes |
|---|---|---|---|
| `limit_for_period` | 50 | 50 | match |
| `limit_refresh_period` | 500ns (`Duration.ofNanos(500)`) | **500µs (`timedelta(microseconds=500)`)** | **deviation** — Python is 1000× longer; the default cycle window is much wider |
| `timeout_duration` | 5s | 5s | match |

The 500µs default makes the out-of-the-box rate "50 permits per 500µs"
≈ 100,000 req/s — close to but not the same as Java's "50 per 500ns".
For any realistic application both values are placeholders that you
must override; the deviation matters mainly for tests that depend on
the default.

### Event semantics

| Java event | Python event | Emitted on |
|---|---|---|
| `RateLimiterOnSuccessEvent` | `RateLimiterOnSuccessEvent` | permission granted (after wait if any) |
| `RateLimiterOnFailureEvent` | `RateLimiterOnFailureEvent` | timeout would be exceeded |
| `RateLimiterOnDrainedEvent` | not implemented | — |

Listener registration: `rl.add_event_listener(EventClass, listener)`.
Listeners registered before the underlying `AtomicRateLimiter` is
materialized are queued and flushed on first use. Listener exceptions
are logged via `logging` at WARNING and execution continues — this is
the only pattern in the port that logs listener failures rather than
silently swallowing them.

### Known deviations

- "Atomic" naming refers to single-step state updates under
  `asyncio.Lock`, not lock-free CAS. Earlier README claims of
  "lock-free" should be read as "atomic-per-call".
- `limit_refresh_period` default is 500µs vs Java's 500ns.
- `RateLimiterOnDrainedEvent` is not emitted.
- Sync decorator path creates a fresh event loop per call (see
  `improvements.md` §1.3 / §2.1) — measurable per-call overhead.

---

## Retry

### API mapping

| Concept | resilience4j (Java) | resilience4py |
|---|---|---|
| Main class | `Retry` | `resilience4py.retry.Retry` |
| Config | `RetryConfig` (builder) | `RetryConfig` (frozen dataclass) |
| Construction | `Retry.of(name, config)` / `RetryRegistry.retry(name)` | `Retry(name, config)` |
| Decoration | `Retry.decorateSupplier(retry, supplier)` | `@retry` (works on sync and async) |
| Manual call | `Retry.executeSupplier(retry, supplier)` | use the decorator wrapper |
| Exhausted exception | `MaxRetriesExceededException` (when configured) | `MaxRetriesExceeded` |
| Interval functions | `IntervalFunction.ofDefaults`, `ofExponentialBackoff`, `ofExponentialRandomBackoff`, `ofRandomized` | `FixedInterval`, `ExponentialBackoff`, `LinearBackoff`, `RandomInterval`, `ExponentialRandomBackoff`, `FibonacciBackoff` |

There is **no** Python `RetryRegistry`.

### Threading & concurrency model

- **Java**: synchronous retries block the calling thread; async wrappers
  use `CompletableFuture` and a scheduler.
- **Python**: async path is the canonical implementation
  (`_execute_with_retry`). The sync decorator branches: if there is
  no running loop it spins one up via `asyncio.new_event_loop()`; if
  a loop is already running it submits a synchronous loop
  (`_execute_sync` using `time.sleep`) to a brand-new
  `ThreadPoolExecutor`. Each invocation creates that executor — there
  is no pool reuse.

### Configuration defaults

| Field (Python) | Java default | Python default | Notes |
|---|---|---|---|
| `max_attempts` | 3 | 3 | match |
| `wait_duration` | 500ms | 500ms | match |
| `interval_function` | `IntervalFunction.ofDefaults()` (returns `wait_duration`) | `None` (falls back to `wait_duration`) | equivalent behavior |
| `retry_on_exception` | retry-everything predicate | `lambda e: True` | match |
| `retry_on_result` | unset | `None` | match |
| `fail_after_max_attempts` | `false` | `False` | match |
| `retry_exceptions` | `[]` (any exception retried) | `None` (any exception retried) | match |
| `abort_exceptions` | `[]` | `None` | match |

### Event semantics

| Java event | Python event | Emitted on |
|---|---|---|
| `RetryOnRetryEvent` | `RetryOnRetryEvent` | scheduled retry after failure |
| `RetryOnSuccessEvent` | `RetryOnSuccessEvent` | call succeeded (any attempt) |
| `RetryOnErrorEvent` | `RetryOnErrorEvent` | retries exhausted, exception escapes |
| `RetryOnIgnoredErrorEvent` | `RetryOnIgnoredErrorEvent` | exception matched `abort_exceptions` or failed `retry_on_exception` |

Listener registration: `retry.on_retry(handler)`, `retry.on_success(...)`,
`retry.on_error(...)`, `retry.on_ignored_error(...)`. This matches
Java's per-event-type registration shape (in contrast to the other
patterns in this port). Listener exceptions are silently swallowed.

### Known deviations

- The synchronous-on-top-of-async branching in `_decorate_sync` (loop
  creation or new `ThreadPoolExecutor` per call) is unique to the Python
  port. Same caveats as the other patterns: per-call overhead and
  fragile interaction with already-running loops.
- `RetryOnSuccessEvent` is emitted on **every** successful attempt,
  including the very first one (`attempt == 1`); Java emits it only when
  there were prior failures. Filter on `event.had_retries` if you only
  care about post-failure success.
- No registry surface.

---

## Cross-cutting deviations

### Registry surface is fragmented

Java exposes a registry per pattern (`CircuitBreakerRegistry`,
`BulkheadRegistry`, `RateLimiterRegistry`, `RetryRegistry`) with a
uniform API: `XRegistry.ofDefaults()`, `XRegistry.of(configs)`, named
factories, registry-wide event consumers, configuration overrides by
name.

In `resilience4py`:

- `CircuitBreaker` exposes `await CircuitBreaker.get_or_create(...)` as a
  classmethod backed by a class-level dict — no shared event consumers,
  no `add_configuration`.
- `RateLimiter` uses a module-level `RateLimiterRegistry` instance
  internally; `RateLimiter.set_default_config()` mutates it but the
  registry is not part of the public surface.
- `Retry` and `Bulkhead` have no registry at all. Instances must be
  tracked by the caller.
- A generic `core.Registry` base class exists but is not used by any
  pattern.

If you rely on resilience4j's centralized registry-based event consumer
pattern, plan to build that layer yourself.

### Event publication and listener guarantees

- All four patterns invoke listeners **inline** on the call path. There
  is no queued/decoupled dispatch out of the box (the
  `core.events.EventPublisher` queue exists but no pattern wires itself
  through it).
- Listener registration shape is **inconsistent**:
  - Circuit Breaker: `on_event(event_type, listener)`
  - Bulkhead: `on_event(handler)` — receives all event types
  - Rate Limiter: `add_event_listener(event_type, listener)`
  - Retry: `on_retry(handler)`, `on_success(handler)`, `on_error(handler)`, `on_ignored_error(handler)`
- Listener exception handling is **inconsistent**:
  - Circuit Breaker, Bulkhead, Retry: exceptions silently swallowed.
  - Rate Limiter: exceptions logged at WARNING via `logging`.

If you need consistent observability, normalize at the application
layer.

### Sync over async execution model

Every pattern exposes a sync decorator path that drives the async
implementation by either (a) creating a new `asyncio` event loop per
call, (b) running the coroutine across an existing loop with
`asyncio.run_coroutine_threadsafe`, or (c) spawning a one-shot
`ThreadPoolExecutor`. This is *not* how Java resilience4j models sync
calls (everything is sync-by-default in Java), and it has practical
consequences:

- Per-call overhead measurable in microseconds-to-milliseconds.
- Fragile inside notebooks, ASGI servers, or any context that already
  owns the running loop.
- Some sync paths in `_decorate_sync` create the loop on the calling
  thread, which means each call pays setup/teardown.

Tracked under `improvements.md` §1.3 and §2.1.

### Patterns from resilience4j that this port does NOT implement

| Java pattern | Status in `resilience4py` |
|---|---|
| `TimeLimiter` (per-call timeout) | not implemented |
| `Cache` (cache-aside helper) | not implemented |
| `Fallback` (typed fallback chain) | not implemented; use try/except in user code |
| `Decorators` (fluent composition: `Decorators.ofSupplier(...).withCircuitBreaker(...).withRetry(...)`) | not implemented; compose decorators directly |
| Reactive (Project Reactor / RxJava) integrations | not applicable |
| Spring Boot starters / Micrometer metrics binders | not implemented |

If you need timeouts today, wrap your async calls with
`asyncio.wait_for(...)` outside the resilience4py decorator chain.

---

## Summary table

| Pattern | Faithful surface | Matching defaults | Notable behavioral deviations |
|---|---|---|---|
| Circuit Breaker | high | mostly | `automatic_transition_from_open_to_half_open=True` (Java: `false`); `OnManualStateTransitionEvent` declared but never emitted |
| Bulkhead (semaphore) | medium | yes | no `BulkheadRegistry`; `on_event` takes a single multi-type handler |
| Bulkhead (thread pool) | medium | **no** | thread-pool sizing constants ignore host CPU; `core_thread_pool_size` unused; `submit()` returns awaited result, not a future |
| Rate Limiter | high | **no** | `limit_refresh_period` default differs by 1000×; "atomic" is not lock-free; `OnDrainedEvent` not emitted |
| Retry | high | yes | `OnSuccessEvent` fires on every success including first attempt; no `RetryRegistry` |

For any unresolved questions about behavior, the source of truth is the
code under `src/resilience4py/`; this document is updated alongside it
but should be re-validated before relying on a specific guarantee.
