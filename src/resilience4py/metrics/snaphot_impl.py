from src.resilience4py.metrics.total_aggregation import TotalAggregation
from src.resilience4py.metrics.snapshot import Snapshot

class SnapshotImpl(Snapshot):

    def __init__(self, total_aggregation:TotalAggregation):
        self.total_duration_in_millis = total_aggregation.total_duration_in_millis
        self.total_number_of_slow_calls = total_aggregation.number_of_slow_calls
        self.total_number_of_slow_failed_calls = total_aggregation.number_of_slow_failed_calls
        self.total_number_of_failed_calls = total_aggregation.number_of_failed_calls
        self.total_number_of_calls = total_aggregation.number_of_calls

    def get_number_of_slow_failed_calls(self):
        return self.total_number_of_slow_failed_calls

    def get_slow_call_rate(self):
        if self.total_number_of_slow_calls == 0:
            return 0
        else:
            return self.total_number_of_slow_calls * 100.0 / self.total_number_of_calls

    def get_number_of_slow_successful_calls(self):
        return self.total_number_of_slow_calls - self.total_number_of_slow_failed_calls

    def get_total_duration(self):
        return self.total_duration_in_millis

    def get_total_number_of_slow_calls(self):
        return self.total_number_of_slow_calls

    def get_total_number_of_slow_failed_calls(self):
        return self.total_number_of_slow_failed_calls

    def get_total_number_of_slow_successful_calls(self):
        return self.total_number_of_slow_calls - self.total_number_of_slow_failed_calls

    def get_slow_calls(self):
        return self.total_number_of_slow_calls

    def get_number_of_successful_calls(self):
        return self.total_number_of_calls-self.total_number_of_failed_calls

    def get_number_of_failed_calls(self):
        return self.total_number_of_failed_calls

    def get_total_number_of_calls(self):
        return self.total_number_of_calls

    def get_failure_rate(self)->float:
        if self.total_number_of_calls == 0:
            return 0
        else:
            return self.total_number_of_failed_calls*100.0/self.total_number_of_calls

    def get_average_duration(self):
        if self.total_number_of_calls==0:
            return 0
        else:
            return self.total_duration_in_millis/self.total_number_of_calls
