from src.resilience4py.metrics.snaphot_impl import SnapshotImpl
from src.resilience4py.metrics.total_aggregation import TotalAggregation


def test_snapshot_impl():
    ta = TotalAggregation()
    ta.number_of_slow_failed_calls =10
    ta.number_of_slow_calls = 10
    ta.number_of_failed_calls = 10
    ta.total_duration_in_millis = 1000
    ta.number_of_calls = 100

    st = SnapshotImpl(ta)
    assert st.total_number_of_calls == 100
    assert st.total_number_of_slow_failed_calls == 10
    assert st.total_number_of_slow_calls == 10
    assert st.total_number_of_failed_calls == 10
    assert st.total_duration_in_millis == 1000
    assert st.get_slow_call_rate() == 10
    assert st.get_failure_rate() == 10
    assert st.get_average_duration() == 10
    assert st.get_number_of_successful_calls() == 90