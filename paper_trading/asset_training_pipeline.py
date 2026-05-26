import logging
import os

import joblib
import pandas as pd
import xgboost as xgb

from features.builder import compute_macro_derived
from features.contract import validate_no_cross_asset_leakage
from features.registry import FEATURE_REGISTRY
from labels.meta_labels import MetaLabelModel
from paper_trading.data_fetcher import fetch_history, fetch_ref

logger = logging.getLogger("quantforge.training_pipeline")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AssetTrainingPipeline:
    def __init__(self, asset):
        self.asset = asset

    def train(self, force=False):
        asset = self.asset
        if os.path.exists(asset.model_path) and not force:
            asset.model = joblib.load(asset.model_path)
            asset._trained = True
            asset._enable_adaptive_macro()
            asset._load_meta_label_model()
            return

        logger.info("%s: downloading history...", asset.name)
        df = fetch_history(asset.ticker)
        ref = fetch_ref("SPY")
        macro = compute_macro_derived(
            pd.read_parquet(os.path.join(BASE, "data/processed/macro_factors.parquet"))
        )
        features = asset._build_features(df, ref, macro)
        validate_no_cross_asset_leakage(features, asset.contract, known_slugs=FEATURE_REGISTRY.keys())
        logger.info("%s: %d feature rows", asset.name, len(features))

        end_date = features.index[-1]
        start_date = end_date - pd.DateOffset(years=asset._retrain_window)
        train = features[features.index >= start_date]
        if len(train) < 200:
            train = features

        X = train[asset.features]
        y = train["label"].astype(int)

        from sklearn.model_selection import train_test_split

        y_vals = set(y.unique())
        if y_vals != {0, 1, 2}:
            logger.warning("%s: train labels only %s — need 3 classes, skipping", asset.name, sorted(y_vals))
            return
        min_class_count = y.value_counts().min()
        strat = y if min_class_count >= 2 else None
        X_tr, X_ev, y_tr, y_ev = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
            stratify=strat,
        )
        if set(y_tr.unique()) != {0, 1, 2}:
            logger.warning("%s: train split classes %s — skipping", asset.name, sorted(set(y_tr.unique())))
            return

        model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=2,
            learning_rate=0.02,
            objective="multi:softprob",
            num_class=3,
            random_state=42,
            n_jobs=1,
            tree_method="hist",
            verbosity=0,
        )
        model.fit(
            X_tr,
            y_tr,
            eval_set=[(X_ev, y_ev)],
            verbose=False,
        )
        asset.model = model
        asset._trained = True
        asset._enable_adaptive_macro()
        joblib.dump(model, asset.model_path)

        # Persist PSI baseline from training feature distribution
        try:
            asset._psi_monitor.persist_baseline(asset.name, X)
        except Exception as e:
            logger.warning("%s: failed to persist PSI baseline: %s", asset.name, e)

        # Train meta-label model
        if asset.config.get("meta_labeling", {}).get("enabled", False):
            asset._meta_label_model = MetaLabelModel(
                threshold=asset.config.get("meta_labeling", {}).get("threshold", 0.55),
            )
            try:
                primary_pred = model.predict_proba(X)
                full_train = train.copy()
                full_train["label"] = y
                asset._meta_label_model.train(full_train, primary_pred, asset.features, asset.name)
            except Exception as e:
                logger.warning("%s: meta-label training failed: %s", asset.name, e)

        # Log feature importances
        asset._window_id_counter += 1
        asset._current_window_train_start = start_date.strftime("%Y-%m-%d")
        asset._current_window_train_end = end_date.strftime("%Y-%m-%d")
        window_id = f"w{asset._window_id_counter}_{asset._current_window_train_end}"
        try:
            asset._importance_store.log_snapshot(
                asset=asset.name,
                feature_names=asset.features,
                importances=model.feature_importances_,
                window_id=window_id,
                train_start=asset._current_window_train_start,
                train_end=asset._current_window_train_end,
                model_type="xgboost",
            )
            stability = asset._importance_store.compute_stability(asset.name)
            if stability is not None:
                asset._last_stability = stability
                logger.info(
                    "%s stability — jaccard=%.3f spearman=%.3f penalty=%.3f",
                    asset.name,
                    stability.jaccard_top_10,
                    stability.spearman_rank_corr,
                    stability.penalty,
                )
        except Exception as e:
            logger.warning("%s: failed to log feature importances: %s", asset.name, e)
