"""FX model loader — loads frozen FX-trained XGBoost models for transfer tests.

FX models are stored in paper_trading/models/{NAME}_model.pkl.
These are pickled XGBoost classifiers trained on tb20 labels with
per-asset feature contracts.

For the transfer test, we identify feature overlap between each FX model
and the target asset (BTC/GC), then apply the model using only
shared features.
"""

import os, sys, pickle, logging
import pandas as pd
import numpy as np

logger = logging.getLogger("quantforge.phase_h.fx_loader")

FX_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                             'paper_trading', 'models')

# FX assets whose models are candidates for transfer testing
# Ordered by feature overlap with BTC/GC
FX_CANDIDATES = {
    'EURAUD': {
        'features': ['rate_diff', 'dxy_mom_21', 'vix_ma21', 'vix_delta_5',
                     'euraud_mom_21', 'euraud_mom_63'],
    },
    'USDCHF': {
        'features': ['rate_diff', 'dxy_mom_21', 'vix_ma21', 'vix_delta_5',
                     'usdchf_mom_21', 'usdchf_mom_63'],
    },
    'GBPUSD': {
        'features': ['rate_diff', 'dxy_mom_21', 'vix_ma21', 'vix_delta_5',
                     'gbpusd_mom_21', 'gbpusd_mom_63'],
    },
    'USDCAD': {
        'features': ['rate_diff', 'dxy_mom_21', 'vix_ma21', 'vix_delta_5',
                     'usdcad_mom_21', 'usdcad_mom_63'],
    },
}


def find_best_transfer_source(target_available_features: list) -> tuple:
    """Find the FX model with most features overlapping the target's available features.

    Args:
        target_available_features: list of feature names available for target asset

    Returns:
        (fx_name, shared_features) tuple, e.g. ('EURAUD', ['rate_diff', 'dxy_mom_21'])
    """
    target_set = set(target_available_features)
    best_name = None
    best_overlap = []
    best_count = 0

    for name, info in FX_CANDIDATES.items():
        fx_features = info['features']
        overlap = [f for f in fx_features if f in target_set]
        if len(overlap) > best_count:
            best_count = len(overlap)
            best_name = name
            best_overlap = overlap

    return best_name, best_overlap


def load_fx_model(name: str):
    """Load a pickled FX XGBoost model.

    Returns None if model file doesn't exist.
    """
    model_path = os.path.join(FX_MODELS_DIR, f'{name}_model.pkl')
    if not os.path.exists(model_path):
        logger.warning('FX model not found: %s', model_path)
        return None
    with open(model_path, 'rb') as f:
        return pickle.load(f)


def fx_transfer_predict(model, X: np.ndarray) -> dict:
    """Apply frozen FX model to target features.

    Returns dict with:
      - signal: predicted class (0=SHORT, 1=NEUTRAL, 2=LONG)
      - proba: array of class probabilities
      - confidence: max probability * 100
    """
    proba = model.predict_proba(X)
    preds = model.predict(X)
    confidence = proba.max(axis=1) * 100

    return {
        'signal': preds.astype(int),
        'proba': proba,
        'confidence': confidence,
    }
