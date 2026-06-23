"""CalibrationRegistry — loads, stores, and applies per-asset calibrators.

Maps (asset_name) -> CalibrationMethod. Loaded at engine start from the
model directory. Used during inference to calibrate raw probabilities.

Registry is explicitly NOT thread-safe — it is loaded once at init and
read-only during inference.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from shared.calibration.calibrator import BetaCalibrator, BinnedCalibrator, CalibrationMethod

logger = logging.getLogger("quantforge.calibration.registry")

CALIBRATOR_TYPES = {
    "BinnedCalibrator": BinnedCalibrator,
    "BetaCalibrator": BetaCalibrator,
}


class CalibrationRegistry:
    """Per-asset calibration model registry.

    Usage:
        registry = CalibrationRegistry()
        registry.load_all(MODEL_DIR / "calibration")
        registry.calibrate("EURUSD", raw_p_long)
    """

    def __init__(self):
        self._calibrators: dict[str, CalibrationMethod] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(self, asset: str, calibrator: CalibrationMethod, metadata: dict[str, Any] | None = None) -> None:
        self._calibrators[asset] = calibrator
        if metadata:
            self._metadata[asset] = metadata

    def get(self, asset: str) -> CalibrationMethod | None:
        return self._calibrators.get(asset)

    def calibrate(self, asset: str, p_long: float | np.ndarray) -> float | np.ndarray:
        cal = self._calibrators.get(asset)
        if cal is None or not cal.fitted:
            return p_long
        return cal.calibrate(np.asarray(p_long, dtype=float))

    def load_all(self, directory: str | Path) -> int:
        """Load all calibrator JSON files from a directory. Returns count loaded."""
        directory = Path(directory)
        if not directory.exists():
            logger.warning("Calibration directory %s does not exist", directory)
            return 0

        count = 0
        for fpath in sorted(directory.glob("*.json")):
            try:
                with open(fpath) as f:
                    data = json.load(f)
                cal_type = data.get("type", "")
                CalibratorCls = CALIBRATOR_TYPES.get(cal_type)
                if CalibratorCls is None:
                    logger.warning("Unknown calibrator type '%s' in %s — skipping", cal_type, fpath.name)
                    continue
                cal = CalibratorCls.load(str(fpath))
                asset = fpath.stem  # filename (without .json) = asset name
                self._calibrators[asset] = cal
                count += 1
                logger.info("Loaded %s for %s (type=%s)", fpath.name, asset, cal_type)
            except Exception as e:
                logger.warning("Failed to load calibrator %s: %s", fpath.name, e)

        logger.info("Loaded %d calibrators from %s", count, directory)
        return count

    def save_all(self, directory: str | Path) -> int:
        """Save all calibrators to JSON files. Returns count saved."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        count = 0
        for asset, cal in self._calibrators.items():
            try:
                cal.save(str(directory / f"{asset}.json"))
                count += 1
            except Exception as e:
                logger.warning("Failed to save calibrator for %s: %s", asset, e)
        logger.info("Saved %d calibrators to %s", count, directory)
        return count

    def available_assets(self) -> list[str]:
        return sorted(self._calibrators.keys())

    def status(self) -> dict[str, Any]:
        return {
            "n_assets": len(self._calibrators),
            "assets": list(self._calibrators.keys()),
            "types": {a: type(c).__name__ for a, c in self._calibrators.items()},
        }
