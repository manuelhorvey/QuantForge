import numpy as np
import pandas as pd


class RegimeClassifier:
    """
    Probabilistic Regime Classifier for institutional gearbox.
    Classifies market into TREND, RANGE, VOLATILE, or NEUTRAL.
    """

    def __init__(self, confidence_threshold: float = 0.45, smoothing_window: int = 10):
        self.confidence_threshold = confidence_threshold
        self.smoothing_window = smoothing_window

    def classify(self, features: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates probabilities for each regime and assigns a final label.
        Uses structural priority for VOLATILE state to ensure shock detection.
        """
        df = features.copy()

        # 1. Structural Priority: VOLATILE
        # Tighten gate slightly to 1.35 to ensure we only catch true shocks
        is_volatile_shock = (df["vol_zscore"] > 1.35) | (df["compression"] > 1.45)

        # 2. Calculate Probabilities for TREND vs RANGE
        # Trend Score: high KER + high ADX
        # Soften multipliers to allow more RANGE capture
        trend_score = (df["kaufman_er"] * 1.3).clip(0, 1.0) * 0.45 + (df["adx"] / 45.0).clip(0, 1.0) * 0.55

        # Range Score: low KER + low ADX + Volatility Compression
        range_score = (
            (1.0 - df["kaufman_er"] * 1.8).clip(0, 1.0) * 0.35
            + (1.0 - df["adx"] / 30.0).clip(0, 1.0) * 0.35
            + (1.0 - df["compression"]).clip(0, 0.5) * 2.0 * 0.3
        )

        # Probabilistic classification for non-shock states
        temp = 2.0
        scores = np.exp(np.array([trend_score, range_score]) * temp)
        probs = scores / scores.sum(axis=0)

        df["P_trend"] = probs[0]
        df["P_range"] = probs[1]
        df["P_volatile"] = 0.0  # Will be set by shock mask

        # 3. Determine Initial Regime
        max_prob = df[["P_trend", "P_range"]].max(axis=1)
        raw_regime = df[["P_trend", "P_range"]].idxmax(axis=1).str.replace("P_", "")

        # Apply NEUTRAL if confidence is low
        df["regime_raw"] = np.where(max_prob < self.confidence_threshold, "neutral", raw_regime)

        # Overwrite with Volatile Shock
        df.loc[is_volatile_shock, "regime_raw"] = "volatile"
        df.loc[is_volatile_shock, "P_volatile"] = 1.0

        # 4. Smoothing Layer (Persistence Constraint)
        mapping = {"trend": 0, "range": 1, "volatile": 2, "neutral": 3}
        reverse_mapping = {v: k for k, v in mapping.items()}

        df["regime_int"] = df["regime_raw"].map(mapping)
        df["regime_smooth_int"] = (
            df["regime_int"]
            .rolling(window=self.smoothing_window)
            .apply(lambda x: pd.Series(x).mode().iloc[0] if not pd.Series(x).mode().empty else x[-1], raw=True)
            .fillna(df["regime_int"])
        )

        df["regime"] = df["regime_smooth_int"].map(reverse_mapping)
        df["regime_confidence"] = max_prob

        return df


if __name__ == "__main__":
    # Test with generated features
    try:
        features = pd.read_parquet("data/processed/EURUSD_regime_features.parquet")
        classifier = RegimeClassifier(confidence_threshold=0.55)
        regime_data = classifier.classify(features)

        print("\nRegime Distribution:")
        print(regime_data["regime"].value_counts(normalize=True))

        print("\nSample Output:")
        print(regime_data[["regime", "P_trend", "P_range", "P_volatile", "regime_confidence"]].tail(10))

        # Save to data/processed
        regime_data.to_parquet("data/processed/EURUSD_regime_labels.parquet")
        print("\nSaved regime labels to data/processed/EURUSD_regime_labels.parquet")

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Classification failed: {e}")
