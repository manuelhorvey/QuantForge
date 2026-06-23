"""Calibration layer — transforms raw model probabilities into well-calibrated ones.

This is P1 in the portfolio maturity framework (probability validity layer).
Calibration runs AFTER model inference but BEFORE signal generation, ensuring
all downstream gates and sizing operate on statistically valid probabilities.

Usage:
    from shared.calibration import BinnedCalibrator, CalibrationRegistry

    # Training (offline):
    cal = BinnedCalibrator(n_bins=10)
    cal.fit(p_long_values, actual_outcomes)  # actual_outcomes: 0=SL, 1=TP

    # Inference (online):
    registry = CalibrationRegistry.load(MODEL_DIR)
    calibrated_p_long = registry.calibrate(asset_name, raw_p_long)
"""

from shared.calibration.calibrator import BinnedCalibrator, BetaCalibrator, CalibrationMethod
from shared.calibration.registry import CalibrationRegistry
from shared.calibration.ece_tracker import ECETracker, compute_ece

__all__ = [
    "BinnedCalibrator",
    "BetaCalibrator",
    "CalibrationMethod",
    "CalibrationRegistry",
    "ECETracker",
    "compute_ece",
]
