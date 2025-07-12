"""Tests for retry interval functions."""

import pytest
import random
from unittest.mock import patch
from resilience4py.retry.interval_functions import (
    IntervalFunction,
    FixedInterval,
    ExponentialBackoff,
    LinearBackoff,
    RandomInterval,
    ExponentialRandomBackoff,
    FibonacciBackoff
)


class TestIntervalFunction:
    """Test suite for the abstract IntervalFunction."""

    def test_abstract_base_class(self):
        """Test that IntervalFunction is abstract."""
        with pytest.raises(TypeError):
            IntervalFunction()

    def test_must_implement_call(self):
        """Test that subclasses must implement __call__."""
        class InvalidInterval(IntervalFunction):
            pass
        
        with pytest.raises(TypeError):
            InvalidInterval()


class TestFixedInterval:
    """Test suite for FixedInterval."""

    def test_fixed_interval_positive(self):
        """Test fixed interval with positive value."""
        interval = FixedInterval(1.5)
        
        assert interval(1) == 1.5
        assert interval(2) == 1.5
        assert interval(10) == 1.5
        assert interval(100) == 1.5

    def test_fixed_interval_zero(self):
        """Test fixed interval with zero value."""
        interval = FixedInterval(0.0)
        
        assert interval(1) == 0.0
        assert interval(5) == 0.0

    def test_fixed_interval_negative_raises(self):
        """Test that negative interval raises ValueError."""
        with pytest.raises(ValueError, match="interval_seconds must be non-negative"):
            FixedInterval(-1.0)

    def test_fixed_interval_large_value(self):
        """Test fixed interval with large value."""
        interval = FixedInterval(3600.0)  # 1 hour
        assert interval(1) == 3600.0


class TestExponentialBackoff:
    """Test suite for ExponentialBackoff."""

    def test_exponential_backoff_default(self):
        """Test exponential backoff with default multiplier."""
        interval = ExponentialBackoff(initial_interval=1.0)
        
        assert interval(1) == 1.0  # 1.0 * (2.0 ** 0)
        assert interval(2) == 2.0  # 1.0 * (2.0 ** 1)
        assert interval(3) == 4.0  # 1.0 * (2.0 ** 2)
        assert interval(4) == 8.0  # 1.0 * (2.0 ** 3)

    def test_exponential_backoff_custom_multiplier(self):
        """Test exponential backoff with custom multiplier."""
        interval = ExponentialBackoff(initial_interval=0.1, multiplier=3.0)
        
        assert interval(1) == pytest.approx(0.1)   # 0.1 * (3.0 ** 0)
        assert interval(2) == pytest.approx(0.3)   # 0.1 * (3.0 ** 1)
        assert interval(3) == pytest.approx(0.9)   # 0.1 * (3.0 ** 2)
        assert interval(4) == pytest.approx(2.7)   # 0.1 * (3.0 ** 3)

    def test_exponential_backoff_with_max_interval(self):
        """Test exponential backoff with maximum interval."""
        interval = ExponentialBackoff(
            initial_interval=1.0,
            multiplier=2.0,
            max_interval=5.0
        )
        
        assert interval(1) == 1.0  # Within limit
        assert interval(2) == 2.0  # Within limit
        assert interval(3) == 4.0  # Within limit
        assert interval(4) == 5.0  # Capped at max
        assert interval(5) == 5.0  # Capped at max

    def test_exponential_backoff_fractional_multiplier(self):
        """Test exponential backoff with fractional multiplier."""
        interval = ExponentialBackoff(initial_interval=10.0, multiplier=0.5)
        
        assert interval(1) == 10.0  # 10.0 * (0.5 ** 0)
        assert interval(2) == 5.0   # 10.0 * (0.5 ** 1)
        assert interval(3) == 2.5   # 10.0 * (0.5 ** 2)
        assert interval(4) == 1.25  # 10.0 * (0.5 ** 3)

    def test_exponential_backoff_validation(self):
        """Test exponential backoff parameter validation."""
        # Negative initial interval
        with pytest.raises(ValueError, match="initial_interval must be non-negative"):
            ExponentialBackoff(initial_interval=-1.0)
        
        # Zero or negative multiplier
        with pytest.raises(ValueError, match="multiplier must be greater than 0"):
            ExponentialBackoff(initial_interval=1.0, multiplier=0.0)
        
        with pytest.raises(ValueError, match="multiplier must be greater than 0"):
            ExponentialBackoff(initial_interval=1.0, multiplier=-2.0)
        
        # Max interval less than initial interval
        with pytest.raises(ValueError, match="max_interval .* must be >= initial_interval"):
            ExponentialBackoff(initial_interval=5.0, max_interval=2.0)

    def test_exponential_backoff_edge_cases(self):
        """Test exponential backoff edge cases."""
        # Zero initial interval
        interval = ExponentialBackoff(initial_interval=0.0)
        assert interval(1) == 0.0
        assert interval(10) == 0.0
        
        # Multiplier of 1 (no growth)
        interval = ExponentialBackoff(initial_interval=5.0, multiplier=1.0)
        assert interval(1) == 5.0
        assert interval(2) == 5.0
        assert interval(10) == 5.0


class TestLinearBackoff:
    """Test suite for LinearBackoff."""

    def test_linear_backoff_default(self):
        """Test linear backoff with default increment."""
        interval = LinearBackoff(initial_interval=1.0)
        
        assert interval(1) == 1.0  # 1.0 + (1.0 * 0)
        assert interval(2) == 2.0  # 1.0 + (1.0 * 1)
        assert interval(3) == 3.0  # 1.0 + (1.0 * 2)
        assert interval(4) == 4.0  # 1.0 + (1.0 * 3)

    def test_linear_backoff_custom_increment(self):
        """Test linear backoff with custom increment."""
        interval = LinearBackoff(initial_interval=0.5, increment=0.25)
        
        assert interval(1) == 0.5   # 0.5 + (0.25 * 0)
        assert interval(2) == 0.75  # 0.5 + (0.25 * 1)
        assert interval(3) == 1.0   # 0.5 + (0.25 * 2)
        assert interval(4) == 1.25  # 0.5 + (0.25 * 3)

    def test_linear_backoff_negative_increment(self):
        """Test linear backoff with negative increment (decreasing)."""
        interval = LinearBackoff(initial_interval=5.0, increment=-1.0)
        
        assert interval(1) == 5.0  # 5.0 + (-1.0 * 0)
        assert interval(2) == 4.0  # 5.0 + (-1.0 * 1)
        assert interval(3) == 3.0  # 5.0 + (-1.0 * 2)
        assert interval(4) == 2.0  # 5.0 + (-1.0 * 3)
        assert interval(6) == 0.0  # Clamped to 0 (5.0 + (-1.0 * 5))
        assert interval(7) == 0.0  # Remains at 0

    def test_linear_backoff_with_max_interval(self):
        """Test linear backoff with maximum interval."""
        interval = LinearBackoff(
            initial_interval=1.0,
            increment=2.0,
            max_interval=5.0
        )
        
        assert interval(1) == 1.0  # Within limit
        assert interval(2) == 3.0  # Within limit
        assert interval(3) == 5.0  # Capped at max
        assert interval(4) == 5.0  # Capped at max

    def test_linear_backoff_validation(self):
        """Test linear backoff parameter validation."""
        # Negative initial interval
        with pytest.raises(ValueError, match="initial_interval must be non-negative"):
            LinearBackoff(initial_interval=-1.0)
        
        # Negative max interval
        with pytest.raises(ValueError, match="max_interval must be non-negative"):
            LinearBackoff(initial_interval=1.0, max_interval=-5.0)

    def test_linear_backoff_zero_increment(self):
        """Test linear backoff with zero increment (constant)."""
        interval = LinearBackoff(initial_interval=2.5, increment=0.0)
        
        assert interval(1) == 2.5
        assert interval(2) == 2.5
        assert interval(10) == 2.5


class TestRandomInterval:
    """Test suite for RandomInterval."""

    def test_random_interval_default(self):
        """Test random interval with default range."""
        interval = RandomInterval()
        
        # Test multiple times to ensure range
        for _ in range(100):
            value = interval(1)  # Attempt number is ignored
            assert 0.0 <= value <= 1.0

    def test_random_interval_custom_range(self):
        """Test random interval with custom range."""
        interval = RandomInterval(min_interval=5.0, max_interval=10.0)
        
        # Test multiple times to ensure range
        for _ in range(100):
            value = interval(1)
            assert 5.0 <= value <= 10.0

    def test_random_interval_same_min_max(self):
        """Test random interval with same min and max (constant)."""
        interval = RandomInterval(min_interval=3.0, max_interval=3.0)
        
        # Should always return the same value
        for _ in range(10):
            assert interval(1) == 3.0

    def test_random_interval_validation(self):
        """Test random interval parameter validation."""
        # Negative min interval
        with pytest.raises(ValueError, match="min_interval must be non-negative"):
            RandomInterval(min_interval=-1.0)
        
        # Max less than min
        with pytest.raises(ValueError, match="max_interval .* must be >= min_interval"):
            RandomInterval(min_interval=5.0, max_interval=2.0)

    @patch('random.uniform')
    def test_random_interval_uses_uniform(self, mock_uniform):
        """Test that random interval uses random.uniform."""
        mock_uniform.return_value = 7.5
        interval = RandomInterval(min_interval=5.0, max_interval=10.0)
        
        result = interval(1)
        assert result == 7.5
        mock_uniform.assert_called_once_with(5.0, 10.0)


class TestExponentialRandomBackoff:
    """Test suite for ExponentialRandomBackoff."""

    def test_exponential_random_backoff_default(self):
        """Test exponential random backoff with default parameters."""
        interval = ExponentialRandomBackoff()
        
        # Test ranges for different attempts
        for _ in range(10):
            assert 0.0 <= interval(1) <= 1.0   # random(0, min(30, 1))
            assert 0.0 <= interval(2) <= 2.0   # random(0, min(30, 2))
            assert 0.0 <= interval(3) <= 4.0   # random(0, min(30, 4))
            assert 0.0 <= interval(4) <= 8.0   # random(0, min(30, 8))
            assert 0.0 <= interval(5) <= 16.0  # random(0, min(30, 16))
            assert 0.0 <= interval(6) <= 30.0  # random(0, min(30, 32)) = 30

    def test_exponential_random_backoff_custom(self):
        """Test exponential random backoff with custom parameters."""
        interval = ExponentialRandomBackoff(
            initial_interval=0.1,
            multiplier=3.0,
            max_interval=1.0
        )
        
        # Test ranges for different attempts
        for _ in range(10):
            assert 0.0 <= interval(1) <= 0.1  # random(0, min(1.0, 0.1))
            assert 0.0 <= interval(2) <= 0.3  # random(0, min(1.0, 0.3))
            assert 0.0 <= interval(3) <= 0.9  # random(0, min(1.0, 0.9))
            assert 0.0 <= interval(4) <= 1.0  # random(0, min(1.0, 2.7)) = 1.0

    def test_exponential_random_backoff_validation(self):
        """Test exponential random backoff parameter validation."""
        # Non-positive initial interval
        with pytest.raises(ValueError, match="initial_interval must be positive"):
            ExponentialRandomBackoff(initial_interval=0.0)
        
        with pytest.raises(ValueError, match="initial_interval must be positive"):
            ExponentialRandomBackoff(initial_interval=-1.0)
        
        # Multiplier <= 1
        with pytest.raises(ValueError, match="multiplier must be greater than 1"):
            ExponentialRandomBackoff(multiplier=1.0)
        
        with pytest.raises(ValueError, match="multiplier must be greater than 1"):
            ExponentialRandomBackoff(multiplier=0.5)
        
        # Non-positive max interval
        with pytest.raises(ValueError, match="max_interval must be positive"):
            ExponentialRandomBackoff(max_interval=0.0)
        
        with pytest.raises(ValueError, match="max_interval must be positive"):
            ExponentialRandomBackoff(max_interval=-10.0)

    @patch('random.uniform')
    def test_exponential_random_backoff_calculation(self, mock_uniform):
        """Test the calculation logic of exponential random backoff."""
        mock_uniform.return_value = 0.5  # Always return middle of range
        
        interval = ExponentialRandomBackoff(
            initial_interval=2.0,
            multiplier=2.0,
            max_interval=10.0
        )
        
        # Attempt 1: random(0, min(10, 2)) = random(0, 2) -> 0.5
        mock_uniform.return_value = 1.0
        assert interval(1) == 1.0
        mock_uniform.assert_called_with(0, 2.0)
        
        # Attempt 3: random(0, min(10, 8)) = random(0, 8) -> 0.5
        mock_uniform.return_value = 4.0
        assert interval(3) == 4.0
        mock_uniform.assert_called_with(0, 8.0)
        
        # Attempt 4: random(0, min(10, 16)) = random(0, 10) -> 0.5
        mock_uniform.return_value = 5.0
        assert interval(4) == 5.0
        mock_uniform.assert_called_with(0, 10.0)


class TestFibonacciBackoff:
    """Test suite for FibonacciBackoff."""

    def test_fibonacci_backoff_default(self):
        """Test Fibonacci backoff with default parameters."""
        interval = FibonacciBackoff()
        
        assert interval(1) == 1.0  # F(1) = 1
        assert interval(2) == 1.0  # F(2) = 1
        assert interval(3) == 2.0  # F(3) = 2
        assert interval(4) == 3.0  # F(4) = 3
        assert interval(5) == 5.0  # F(5) = 5
        assert interval(6) == 8.0  # F(6) = 8
        assert interval(7) == 13.0 # F(7) = 13

    def test_fibonacci_backoff_custom_initial(self):
        """Test Fibonacci backoff with custom initial interval."""
        interval = FibonacciBackoff(initial_interval=0.5)
        
        assert interval(1) == 0.5  # 0.5 * 1
        assert interval(2) == 0.5  # 0.5 * 1
        assert interval(3) == 1.0  # 0.5 * 2
        assert interval(4) == 1.5  # 0.5 * 3
        assert interval(5) == 2.5  # 0.5 * 5

    def test_fibonacci_backoff_with_max_interval(self):
        """Test Fibonacci backoff with maximum interval."""
        interval = FibonacciBackoff(initial_interval=1.0, max_interval=10.0)
        
        assert interval(1) == 1.0   # Within limit
        assert interval(2) == 1.0   # Within limit
        assert interval(3) == 2.0   # Within limit
        assert interval(4) == 3.0   # Within limit
        assert interval(5) == 5.0   # Within limit
        assert interval(6) == 8.0   # Within limit
        assert interval(7) == 10.0  # Capped at max (would be 13)
        assert interval(8) == 10.0  # Capped at max (would be 21)

    def test_fibonacci_backoff_validation(self):
        """Test Fibonacci backoff parameter validation."""
        # Non-positive initial interval
        with pytest.raises(ValueError, match="initial_interval must be positive"):
            FibonacciBackoff(initial_interval=0.0)
        
        with pytest.raises(ValueError, match="initial_interval must be positive"):
            FibonacciBackoff(initial_interval=-1.0)
        
        # Non-positive max interval
        with pytest.raises(ValueError, match="max_interval must be positive"):
            FibonacciBackoff(initial_interval=1.0, max_interval=0.0)
        
        with pytest.raises(ValueError, match="max_interval must be positive"):
            FibonacciBackoff(initial_interval=1.0, max_interval=-5.0)

    def test_fibonacci_caching(self):
        """Test that Fibonacci numbers are cached."""
        interval = FibonacciBackoff()
        
        # First access populates cache
        assert interval(5) == 5.0
        
        # Check cache contains expected values
        assert interval._fib_cache[1] == 1
        assert interval._fib_cache[2] == 1
        assert interval._fib_cache[3] == 2
        assert interval._fib_cache[4] == 3
        assert interval._fib_cache[5] == 5
        
        # Accessing again should use cache
        assert interval(5) == 5.0
        assert interval(3) == 2.0

    def test_fibonacci_edge_cases(self):
        """Test Fibonacci backoff edge cases."""
        interval = FibonacciBackoff()
        
        # Zero or negative attempts should be treated as 1
        assert interval(0) == 1.0  # F(1)
        assert interval(-1) == 1.0  # F(1)
        
        # Large attempt number
        assert interval(10) == 55.0  # F(10) = 55
        assert interval(15) == 610.0  # F(15) = 610