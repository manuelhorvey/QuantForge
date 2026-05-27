from dataclasses import dataclass
from enum import Enum


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    FLAT = "FLAT"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class ValidityState(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class LiquidityRegime(str, Enum):
    NORMAL = "NORMAL"
    THIN = "THIN"
    STRESSED = "STRESSED"


@dataclass
class MarketStructureState:
    """
    Structural snapshot of the market.
    Purely informational, no decision logic.
    """
    trend_strength: float
    compression_score: float
    distance_to_swing_high: float
    distance_to_swing_low: float
    volatility_regime: float
    breakout_pressure: float


class EntryAction(str, Enum):
    ENTER = "ENTER"
    DEFER = "DEFER"
    SKIP = "SKIP"
    EXIT = "EXIT"


@dataclass(frozen=True)
class PolicyDecision:
    """
    Immutable execution instruction packet.
    Frozen orchestration of signal, timing, and reward.
    """
    action: EntryAction
    entry_plan: object | None  # PositionIntent | DeferredEntry
    exit_plan: object | None   # TPGeometry
    reason: str
    archetype: str
    metadata: dict


@dataclass(frozen=True)
class TPGeometry:
    """
    Immutable reward geometry generated at entry.
    Locked and path-independent execution schedule.
    """
    tp_distance: float
    scale_out_tiers: list[tuple[float, float]]  # [(fraction, multiplier)]
    convexity_score: float
    metadata: dict


@dataclass
class TradeDecision:
    """
    Pure model intent — what the model wants to do.
    No execution details, no side effects.
    """

    asset: str
    signal: SignalType
    label: int
    confidence: float
    prob_long: float
    prob_short: float
    prob_neutral: float
    close_price: float
    timestamp: str
    position_size: float
    archetype: str = "UNKNOWN"


@dataclass
class PositionIntent:
    """
    Execution expression — how to implement a TradeDecision.
    Concrete entry, stop-loss, take-profit, and vol.
    """

    side: PositionSide
    entry_price: float
    entry_date: str
    stop_loss: float
    take_profit: float
    vol: float

    @classmethod
    def from_price_and_vol(
        cls, side: PositionSide, entry_price: float, entry_date: str, vol: float, sl_mult: float = 1.0, tp_mult: float = 2.5
    ) -> "PositionIntent":
        if side == PositionSide.LONG:
            sl = entry_price * (1 - vol * sl_mult)
            tp = entry_price * (1 + vol * tp_mult)
        else:
            sl = entry_price * (1 + vol * sl_mult)
            tp = entry_price * (1 - vol * tp_mult)
        return cls(side=side, entry_price=entry_price, entry_date=entry_date, stop_loss=sl, take_profit=tp, vol=vol)
