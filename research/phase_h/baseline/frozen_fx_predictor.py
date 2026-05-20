"""Frozen FX predictor — applies FX-trained models to BTC/GC.

MODE A: FX-FROZEN TRANSFER TEST (CONTROL):
  - Uses the best-matching FX model for the target asset
  - Builds features using ONLY the feature overlap between FX and target
  - No retraining, no adaptation
  - Outputs predictions + metrics for transfer test evaluation
"""

import os, sys, json, logging
import pandas as pd
import numpy as np

logger = logging.getLogger("quantforge.phase_h.fx_predictor")

FX_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                             'paper_trading', 'models')


def run_fx_transfer_test(
    target_name: str,
    features_df: pd.DataFrame,
    available_features: list,
) -> dict:
    """Run the FX-frozen transfer test for a target asset.

    Args:
        target_name: 'BTC' or 'GC'
        features_df: DataFrame with all available features for target asset
        available_features: list of feature names available in features_df

    Returns:
        dict with transfer test predictions or error status
    """
    from research.phase_h.baseline.fx_model_loader import (
        find_best_transfer_source, load_fx_model, fx_transfer_predict
    )

    # 1. Find best FX model for transfer
    best_source, shared_features = find_best_transfer_source(available_features)
    if best_source is None or len(shared_features) < 2:
        logger.warning('%s: insufficient feature overlap for FX transfer (found=%s, n=%d)',
                       target_name, best_source, len(shared_features or []))
        return {'status': 'failed', 'reason': 'insufficient_feature_overlap'}

    logger.info('%s: FX transfer source=%s, shared=%s',
                target_name, best_source, shared_features)

    # 2. Load FX model
    model = load_fx_model(best_source)
    if model is None:
        return {'status': 'failed', 'reason': 'model_not_found'}

    # 3. Apply model to target features (pad missing features with 0)
    from research.phase_h.baseline.fx_model_loader import FX_CANDIDATES
    fx_full_features = FX_CANDIDATES[best_source]['features']
    X_full = np.zeros((len(features_df), len(fx_full_features)))
    for j, f in enumerate(fx_full_features):
        if f in shared_features:
            X_full[:, j] = features_df[f].values
    result = fx_transfer_predict(model, X_full)

    return {
        'status': 'ok',
        'fx_source': best_source,
        'shared_features': shared_features,
        'n_features': len(shared_features),
        'n_bars': len(features_df),
        'n_directional': int((result['signal'] != 1).sum()),
        'signal': result['signal'].tolist(),
        'confidence': [round(c, 2) for c in result['confidence']],
        'signal_distribution': {
            'short': int((result['signal'] == 0).sum()),
            'neutral': int((result['signal'] == 1).sum()),
            'long': int((result['signal'] == 2).sum()),
        },
    }
