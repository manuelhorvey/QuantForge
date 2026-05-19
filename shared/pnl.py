from abc import ABC, abstractmethod


class PnLStrategy(ABC):
    @abstractmethod
    def compute_daily(
        self,
        current_value: float,
        direction: int,
        ret: float,
        position_size_fraction: float,
        pos_size: float = 1.0,
    ) -> float:
        ...


class DefaultPnLStrategy(PnLStrategy):
    def compute_daily(
        self,
        current_value: float,
        direction: int,
        ret: float,
        position_size_fraction: float,
        pos_size: float = 1.0,
    ) -> float:
        return current_value * direction * ret * position_size_fraction * pos_size
