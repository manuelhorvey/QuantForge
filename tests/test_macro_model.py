import pytest
import pandas as pd
import numpy as np
from models.macro_only import MacroOnlyModel, FEATURES

def test_macro_model_init():
    model = MacroOnlyModel()
    assert model.model is not None
    assert model.scaler is not None

def test_macro_model_fit_predict():
    model = MacroOnlyModel()
    
    # Create dummy data
    np.random.seed(42)
    n_samples = 100
    X = pd.DataFrame(np.random.randn(n_samples, len(FEATURES)), columns=FEATURES)
    y = np.random.randint(0, 3, n_samples)
    
    X_val = pd.DataFrame(np.random.randn(20, len(FEATURES)), columns=FEATURES)
    y_val = np.random.randint(0, 3, 20)
    
    model.fit(X, y, X_val, y_val)
    
    probs = model.predict_proba(X_val)
    assert probs.shape == (20, 3)
    assert np.allclose(probs.sum(axis=1), 1.0)

def test_macro_model_predict_without_fit_raises():
    model = MacroOnlyModel()
    X = pd.DataFrame(np.random.randn(10, len(FEATURES)), columns=FEATURES)
    # Scaler hasn't been fit, but XGBoost might also complain
    with pytest.raises(Exception):
        model.predict_proba(X)
