from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class ModelInterface(ABC):
    @abstractmethod
    def predict(self, model, X: pd.DataFrame) -> np.ndarray: ...


class XGBoostModel(ModelInterface):
    def predict(self, model, X: pd.DataFrame) -> np.ndarray:
        return model.predict_proba(X)
