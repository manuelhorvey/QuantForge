from dataclasses import dataclass, field
from typing import Any


@dataclass
class TradingContext:
    broker: Any = None
    state_store: Any = None
    execution_bridge: Any = None
    wal_writer: Any = None
    config: dict | None = None
    cycle_id: int = 0


@dataclass
class WorkingState:
    _trained: bool = False
    _cycle_counter: int = 0
    _kelly_multiplier: float = 1.0
    _calibration_applied: bool = False

    _entry_price: float | None = None
    _entry_vol: Any = None
    _entry_signal_dir: int = 0
    _entry_archetype: str = "UNKNOWN"
    _entry_pressure: Any = None
    _entry_validity_state: str = "YELLOW"
    _bars_at_entry: int = 0
    _last_adjust_bar: int = 0
    _initial_sl: Any = None
    _initial_tp: Any = None
    _last_entry_slippage: float = 0.0
    _last_policy_hash: str = ""
    _regime_adjusted_entry: bool = False
    _cooldown_score: float = 0.0
    _last_cooldown_update_cycle: int = -999
    _last_signal_flip_cycle: int = -6
    _min_flip_interval_bars: int = 3
    _churn_ratio_threshold: float = 0.50
    _initial_settlement_done: bool = False
    _scale_out_plan: Any = None
    _pending_entries: dict[str, Any] = field(default_factory=dict)
    _deferred_entry: Any = None

    _mt5_cleanup_queue: list[tuple[str, int]] = field(default_factory=list)
    _mt5_cleanup_retries: int = 0

    _last_spread_bps: float | None = None
    _last_spread_time: float = 0.0
    _spread_tier: str = "fx_cross"

    _last_feature_vector: dict[str, float] | None = None
    _last_feature_hash: str = ""
    _last_feature_schema: list[str] | None = None
    _last_label: Any = None
    _last_confidence: float = 0.0
    _last_prob_long: float = 0.0
    _last_prob_short: float = 0.0
    _last_prob_neutral: float = 0.0
    _last_macro_dir: Any = None
    _last_blend_dir: Any = None
    _regime_bar_counter: int = 0
    _ensemble_breakdown: dict = field(default_factory=dict)
    _window_id_counter: int = 0
    _current_window_train_start: str = ""
    _current_window_train_end: str = ""
    _last_stability: Any = None
    _last_psi_drift: Any = None
    _last_gates_trace: dict[str, bool] | None = None
    _last_sizing_chain: dict[str, float] | None = None
    _truncate_inference: bool = False
    _psi_drift_initialized: bool = False
    _suppress_until: float = 0.0

    _risk_signal: Any = None
    _shadow_action: Any = None
    _shadow_drift_intel: Any = None
    _shadow_learning: Any = None

    _experiment_id: str = ""
    _attribution_export_dir: Any = None
    _current_trade_id: Any = None
    _attribution_buffer: list = field(default_factory=list)
