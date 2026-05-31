import pytest
import pandas as pd
import numpy as np
from models.mean_reversion.mr_model import MeanReversionModel

def test_mr_model_predict_returns_series():
    model = MeanReversionModel()
    features = pd.DataFrame({
        'rsi': [20, 50, 80],
        'bb_zscore': [-2, 0, 2]
    })
    probs = model.predict(features)
    assert isinstance(probs, pd.Series)
    assert len(probs) == 3

def test_mr_model_logic():
    model = MeanReversionModel()
    # Oversold: RSI=30, Z=-2 -> Should be High Prob (1.0)
    features_oversold = pd.DataFrame({'rsi': [30], 'bb_zscore': [-2]})
    prob_oversold = model.predict(features_oversold).iloc[0]
    
    # Formula: 
    # rsi_prob = (70 - 30) / 40 = 1.0
    # z_prob = (2 - (-2)) / 4 = 1.0
    # prob = (1.0 + 1.0) / 2 = 1.0
    assert prob_oversold == 1.0

    # Overbought: RSI=70, Z=2 -> Should be Low Prob (0.0)
    features_overbought = pd.DataFrame({'rsi': [70], 'bb_zscore': [2]})
    prob_overbought = model.predict(features_overbought).iloc[0]
    
    # Formula:
    # rsi_prob = (70 - 70) / 40 = 0.0
    # z_prob = (2 - 2) / 4 = 0.0
    # prob = (0.0 + 0.0) / 2 = 0.0
    assert prob_overbought == 0.0

def test_mr_model_clipping():
    model = MeanReversionModel()
    # Extremely Oversold
    features = pd.DataFrame({'rsi': [10], 'bb_zscore': [-5]})
    prob = model.predict(features).iloc[0]
    assert prob == 1.0

    # Extremely Overbought
    features = pd.DataFrame({'rsi': [90], 'bb_zscore': [5]})
    prob = model.predict(features).iloc[0]
    assert prob == 0.0
