"""Calibration models — transforms raw binary classifier probabilities.

Two implementations:
    1. BinnedCalibrator — non-parametric, robust, recommended default.
        Divides [0, 1] into equal-width bins; each bin stores the empirical
        P(positive | bin). Linear interpolation between bin centers.

        2. BetaCalibrator — parametric, smoother, requires more data.
       Fits a Beta distribution to the logit of predictions via
       maximum likelihood. More sample-efficient but less robust
       to distribution shift.

Both implement the CalibrationMethod protocol:
    fit(p_long, outcomes) -> Self
    calibrate(p_long) -> np.ndarray
    save(path) / load(path)
"""

from __future__ import annotations

import json
import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

import numpy as np

logger = logging.getLogger("quantforge.calibration")


def compute_ece(
    probs: np.ndarray,
    outcomes: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error."""
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    if len(probs) < n_bins:
        return 0.0
    bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n_total = len(probs)
    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        in_bin = (probs >= lo) & (probs < hi)
        if i == n_bins - 1:
            in_bin |= probs == 1.0
        n_bin = in_bin.sum()
        if n_bin > 0:
            bin_acc = outcomes[in_bin].mean()
            bin_conf = probs[in_bin].mean()
            ece += (n_bin / n_total) * abs(bin_acc - bin_conf)
    return float(ece)


class CalibrationMethod(ABC):
    """Protocol for a probability calibration model."""

    fitted: bool = False

    @abstractmethod
    def fit(self, p_long: np.ndarray, outcomes: np.ndarray) -> Self: ...

    @abstractmethod
    def calibrate(self, p_long: np.ndarray) -> np.ndarray: ...

    @abstractmethod
    def save(self, path: str | Path) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> Self: ...


class BinnedCalibrator(CalibrationMethod):
    """Non-parametric binned calibration with linear interpolation.

    Divides [0, 1] into n_bins equal-width bins. Each bin stores the
    empirical P(outcome=1 | bin). Calibration uses linear interpolation
    between bin centers. Extrapolation clamps to nearest bin center.

    This is the RECOMMENDED default — robust to fold-to-fold distribution
    shift, no distributional assumptions, and reliable with >=50 samples.

    Reference: Zadrozny & Elkan (2001), "Obtaining calibrated probability
    estimates from decision trees and naive Bayesian classifiers."
    """

    def __init__(self, n_bins: int = 10, min_samples_per_bin: int = 5):
        self.n_bins = n_bins
        self.min_samples_per_bin = min_samples_per_bin
        self.bin_centers: np.ndarray | None = None
        self.bin_empirical_probs: np.ndarray | None = None
        self.fitted = False

    def fit(self, p_long: np.ndarray, outcomes: np.ndarray) -> Self:
        p_long = np.asarray(p_long, dtype=float)
        outcomes = np.asarray(outcomes, dtype=int)

        bin_boundaries = np.linspace(0.0, 1.0, self.n_bins + 1)
        centers = np.empty(self.n_bins)
        empirical = np.empty(self.n_bins)

        for i in range(self.n_bins):
            lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
            in_bin = (p_long >= lo) & (p_long < hi)
            if i == self.n_bins - 1:
                in_bin |= p_long == 1.0
            centers[i] = (lo + hi) / 2.0
            n_bin = in_bin.sum()
            if n_bin >= self.min_samples_per_bin:
                empirical[i] = outcomes[in_bin].mean()
            else:
                empirical[i] = 0.5  # neutral fallback for sparse bins

        self.bin_centers = centers
        self.bin_empirical_probs = empirical
        self.fitted = True
        return self

    def calibrate(self, p_long: np.ndarray) -> np.ndarray:
        if not self.fitted or self.bin_centers is None or self.bin_empirical_probs is None:
            logger.warning("BinnedCalibrator not fitted — returning raw probabilities")
            return np.asarray(p_long, dtype=float)

        p_long = np.asarray(p_long, dtype=float).ravel()
        result = np.interp(p_long, self.bin_centers, self.bin_empirical_probs)
        return np.clip(result, 0.001, 0.999)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "type": "BinnedCalibrator",
            "n_bins": self.n_bins,
            "min_samples_per_bin": self.min_samples_per_bin,
            "bin_centers": self.bin_centers.tolist() if self.bin_centers is not None else None,
            "bin_empirical_probs": self.bin_empirical_probs.tolist() if self.bin_empirical_probs is not None else None,
        }
        with open(path, "w") as f:
            json.dump(data, f)
        logger.info("Saved BinnedCalibrator to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> Self:
        path = Path(path)
        with open(path) as f:
            data = json.load(f)
        n_bins = int(data["n_bins"])
        min_samples = int(data.get("min_samples_per_bin", 5))
        cal = cls(n_bins=n_bins, min_samples_per_bin=min_samples)
        if data.get("bin_centers") is not None:
            cal.bin_centers = np.array(data["bin_centers"], dtype=float)
            cal.bin_empirical_probs = np.array(data["bin_empirical_probs"], dtype=float)
            cal.fitted = True
        return cal


class BetaCalibrator(CalibrationMethod):
    """Beta calibration — 3-parameter transformation using Beta distribution.

    Fits: calibrated_p = 1 / (1 + exp(-(a * logit(p) + b)))
    where logit(p) = log(p / (1 - p)).

    This is a special case of Beta calibration (Kull, Silva Filho & Flach, 2017)
    that corresponds to the Beta(alpha, beta) CDF. More flexible than Platt
    scaling (which is a special case with fixed shape), but more stable than
    isotonic regression.

    Requires MORE data than BinnedCalibrator (recommended >=200 samples).
    """

    def __init__(self):
        self.a: float = 1.0
        self.b: float = 0.0
        self.fitted = False

    def fit(self, p_long: np.ndarray, outcomes: np.ndarray) -> Self:
        p_long = np.asarray(p_long, dtype=float)
        outcomes = np.asarray(outcomes, dtype=int)

        # Clip to avoid log(0)
        eps = 1e-6
        p = np.clip(p_long, eps, 1.0 - eps)
        logit_p = np.log(p / (1.0 - p))

        from scipy.optimize import minimize

        def neg_log_likelihood(params):
            a, b = params
            logits = a * logit_p + b
            pred = 1.0 / (1.0 + np.exp(-logits))
            pred = np.clip(pred, eps, 1.0 - eps)
            return -np.sum(outcomes * np.log(pred) + (1.0 - outcomes) * np.log(1.0 - pred))

        result = minimize(neg_log_likelihood, [1.0, 0.0], method="L-BFGS-B")
        if result.success:
            self.a, self.b = result.x
            self.fitted = True
        else:
            logger.warning("BetaCalibrator fit failed: %s — using identity", result.message)
            self.a, self.b = 1.0, 0.0
            self.fitted = False
        return self

    def calibrate(self, p_long: np.ndarray) -> np.ndarray:
        if not self.fitted:
            logger.warning("BetaCalibrator not fitted — returning raw probabilities")
            return np.asarray(p_long, dtype=float)

        p_long = np.asarray(p_long, dtype=float)
        eps = 1e-6
        p = np.clip(p_long, eps, 1.0 - eps)
        logit_p = np.log(p / (1.0 - p))
        logits = self.a * logit_p + self.b
        calibrated = 1.0 / (1.0 + np.exp(-logits))
        return np.clip(calibrated, 0.001, 0.999)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "type": "BetaCalibrator",
            "a": self.a,
            "b": self.b,
        }
        with open(path, "w") as f:
            json.dump(data, f)
        logger.info("Saved BetaCalibrator to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> Self:
        path = Path(path)
        with open(path) as f:
            data = json.load(f)
        cal = cls()
        cal.a = float(data["a"])
        cal.b = float(data["b"])
        cal.fitted = True
        return cal
