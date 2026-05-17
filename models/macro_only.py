from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
import pandas as pd
import numpy as np

FEATURES = [
    'rate_diff',
    '2y_yield_delta_63',
    'xlf_mom_63',
    'xlf_vs_spy_63',
]

class MacroOnlyModel:
    def __init__(self):
        self.model = XGBClassifier(
            max_depth             = 2,
            n_estimators          = 300,
            learning_rate         = 0.02,
            subsample             = 0.8,
            colsample_bytree      = 1.0,
            min_child_weight      = 15,
            reg_alpha             = 0.5,
            reg_lambda            = 2.0,
            early_stopping_rounds = 30,
            eval_metric           = 'mlogloss',
            objective             = 'multi:softprob',
            num_class             = 3,
        )
        self.scaler = StandardScaler()

    def fit(self, X, y, X_val, y_val):
        Xs = self.scaler.fit_transform(X[FEATURES])
        Xv = self.scaler.transform(X_val[FEATURES])
        self.model.fit(
            Xs, y,
            eval_set=[(Xv, y_val)],
            verbose=False,
        )

    def predict_proba(self, X):
        return self.model.predict_proba(
            self.scaler.transform(X[FEATURES])
        )
