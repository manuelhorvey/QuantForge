import logging

import numpy as np
import pandas as pd

from labels.meta_labels import MetaLabelModel

logger = logging.getLogger("quantforge.signal_service")


class SignalService:
    def __init__(self, asset):
        self.asset = asset

    def load_meta_label_model(self) -> None:
        asset = self.asset
        if not asset.config.get("meta_labeling", {}).get("enabled", False):
            return
        try:
            model = MetaLabelModel(
                threshold=asset.config.get("meta_labeling", {}).get("threshold", 0.55),
            )
            model._load(model._model_path(asset.name))
            if model._trained:
                asset._meta_label_model = model
                logger.info("%s: meta-label model loaded from cache", asset.name)
        except Exception as e:
            logger.debug("%s: no cached meta-label model: %s", asset.name, e)

    def meta_size_multiplier(self) -> float:
        asset = self.asset
        if not asset.config.get("meta_labeling", {}).get("enabled", False):
            return 1.0
        meta_proba = getattr(asset, "_last_meta_proba", None)
        if meta_proba is None:
            return 1.0

        threshold = asset.config.get("meta_labeling", {}).get("threshold", 0.55)
        min_size = asset.config.get("meta_labeling", {}).get("min_size_on_threshold", 0.25)

        if meta_proba < threshold:
            return 0.0
        if meta_proba >= 1.0:
            return 1.0

        t = (meta_proba - threshold) / (1.0 - threshold)
        return min_size + t * (1.0 - min_size)

    def enable_adaptive_macro(self) -> None:
        asset = self.asset
        if not asset.config.get("adaptive_macro") or asset.model is None:
            return
        macro_head = getattr(asset.model, "macro_head", None)
        if macro_head is not None:
            macro_head.online_weight = True
