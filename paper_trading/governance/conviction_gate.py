import logging
from typing import TypedDict

logger = logging.getLogger("quantforge.conviction_gate")


class RegimeRow(TypedDict):
    P_trend: float
    P_range: float
    P_volatile: float
    regime_label: str


def evaluate_regime_conviction_gate(
    regime_row: RegimeRow | None,
    model_confidence: float,
    bars_in_current_regime: int,
    regime_margin_threshold: float,
    confidence_threshold: float,
    min_bars_in_regime: int,
) -> tuple[bool, str]:
    """
    AND-gate: only allow flip when regime conviction is high AND
    the model is uncertain (confidence below threshold).

    This catches the case where the market structure has clearly
    shifted but the model is lagging — defer to the regime signal.

    Exits (all pass-through):
      1. no_regime_data     — classifier not yet run (cold start).
      2. volatile_bypass    — structural shock override is unambiguous.
      3. model_aligned      — model is already confident in the
                              flip direction; bypasses regime stability
                              check since confidence is itself evidence
                              the flip is valid.

    Blocks:
      4. regime_margin_below_threshold — trend/range margin too low.
      5. regime_not_stable             — regime hasn't held long enough.

    Returns (True, reason) if the flip is allowed, (False, reason) if blocked.
    """
    # 1. No regime data available — pass through.
    #    Intentional: the gate is disabled during cold start (classifier
    #    hasn't run yet). Once the classifier fires on the next cycle
    #    the row will be populated and the gate engages automatically.
    if regime_row is None:
        return True, "no_regime_data"

    # 2. Structural shock bypass — volatile override is unambiguous
    pv = regime_row.get("P_volatile", 0.0)
    if pv == 1.0:
        return True, "volatile_bypass"

    # 3. If model is already confident, no need to gate
    if model_confidence > confidence_threshold:
        return True, "model_aligned"

    # 4. Regime conviction check — margin must be strong
    pt = regime_row.get("P_trend", 0.5)
    pr = regime_row.get("P_range", 0.5)
    margin = abs(pt - pr)
    if margin < regime_margin_threshold:
        return False, f"regime_margin_below_threshold_{margin:.3f}"

    # 5. Regime must be stable (not just flipped one bar ago)
    if bars_in_current_regime < min_bars_in_regime:
        return False, f"regime_not_stable_{bars_in_current_regime}"

    return True, "gate_passed"
