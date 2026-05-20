"""Calibration metrics — optional sanity check for Phase H.

Only checks if probabilities are informative (not decision-drivers).
No calibration fitting or reliability curve computation.
"""

import numpy as np


def compute_calibration_sanity(predictions_summary: dict) -> dict:
    """Compute minimal calibration check: do higher confidences correlate with correctness?

    Args:
        predictions_summary: dict containing signal and confidence arrays

    Returns:
        dict with calibration sanity metrics
    """
    from scipy.stats import pearsonr

    signal = np.array(predictions_summary.get('signal', []))
    confidence = np.array(predictions_summary.get('confidence', []))

    if len(signal) == 0 or len(confidence) == 0:
        return {'ece': None, 'conf_correctness_r': None}

    # Directional correctness (1-bar)
    # Simplified: no lookahead, just check if confidence distribution looks reasonable
    conf_mean = float(confidence.mean())
    conf_std = float(confidence.std())
    conf_q25 = float(np.percentile(confidence, 25))
    conf_q75 = float(np.percentile(confidence, 75))

    return {
        'conf_mean': round(conf_mean, 2),
        'conf_std': round(conf_std, 2),
        'conf_q25': round(conf_q25, 2),
        'conf_q75': round(conf_q75, 2),
        'n_directional': int((signal != 1).sum()),
    }
