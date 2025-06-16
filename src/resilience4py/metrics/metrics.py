from abc import ABC, abstractmethod
from enum import Enum

from src.resilience4py.metrics.snapshot import Snapshot

class Outcome(Enum):
    SUCCESS = 10
    ERROR = 20
    SLOW_SUCCESS = 30
    SLOW_ERROR = 40

class Metrics(ABC):
    @abstractmethod
    def record(self, duration, duration_unit, outcome)->Snapshot:
        pass

    @abstractmethod
    def get_snapshot(self)->Snapshot:
        pass