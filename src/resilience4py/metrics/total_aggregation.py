from src.resilience4py.metrics.abstract_aggregation import AbstractAggregation
from src.resilience4py.metrics.metrics import Outcome


class TotalAggregation(AbstractAggregation):

    def record(self, duration: int, outcome: Outcome) -> None:
        pass

    def remove_bucket(self, bucket:AbstractAggregation)->None:
        self.total_duration_in_millis -= bucket.total_duration_in_millis
        self.number_of_slow_calls -= bucket.number_of_slow_calls
        self.number_of_slow_failed_calls -= bucket.number_of_slow_failed_calls
        self.number_of_failed_calls -= bucket.number_of_failed_calls
        self.number_of_calls -= bucket.number_of_calls