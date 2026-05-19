from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd

from features.builder import build_features, compute_macro_derived
from features.contract import FeatureContract


class FeaturePipeline(ABC):
    @abstractmethod
    def build(
        self,
        df: pd.DataFrame,
        macro: pd.DataFrame,
        ref: Optional[pd.DataFrame],
        contract: FeatureContract,
    ) -> pd.DataFrame:
        ...

    @abstractmethod
    def macro_derived(self, macro_df: pd.DataFrame) -> pd.DataFrame:
        ...


class DefaultFeaturePipeline(FeaturePipeline):
    def build(
        self,
        df: pd.DataFrame,
        macro: pd.DataFrame,
        ref: Optional[pd.DataFrame],
        contract: FeatureContract,
    ) -> pd.DataFrame:
        return build_features(df, macro, ref, contract)

    def macro_derived(self, macro_df: pd.DataFrame) -> pd.DataFrame:
        return compute_macro_derived(macro_df)
