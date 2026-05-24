import numpy as np
import pandas as pd


def get_volatility(close: pd.Series, span: int = 100) -> pd.Series:
    """
    Computes volatility as the rolling standard deviation of log returns.
    """
    returns = np.log(close / close.shift(1))
    vol = returns.ewm(span=span).std()
    return vol.dropna()


def apply_triple_barrier(
    df: pd.DataFrame, pt_sl: list = [1, 1], target: pd.Series = None, vertical_barrier: int = 5
) -> pd.DataFrame:
    """
    Applies Triple Barrier Labeling.

    Args:
        df: DataFrame with 'close' prices
        pt_sl: Multipliers for profit taking [pt] and stop loss [sl]
        target: Target volatility or fixed width for barriers.
                If None, uses daily vol.
        vertical_barrier: Number of bars for timeout.

    Returns:
        pd.DataFrame: Original data with 'label' column
    """
    if target is None:
        target = get_volatility(df["close"])

    # Align df with target (volatility calculation might drop rows)
    df = df.loc[target.index].copy()

    # Initialize labels
    labels = pd.Series(index=df.index, data=0)

    # Iterate through each timestamp
    for i in range(len(df) - vertical_barrier):
        current_idx = df.index[i]
        current_price = df["close"].iloc[i]

        # Determine barrier widths
        vol = target.loc[current_idx]
        upper_barrier = current_price * (1 + vol * pt_sl[0])
        lower_barrier = current_price * (1 - vol * pt_sl[1])

        # Look ahead up to the vertical barrier
        future_prices = df["close"].iloc[i + 1 : i + vertical_barrier + 1]

        # Check if either horizontal barrier is hit
        hits_upper = future_prices[future_prices >= upper_barrier]
        hits_lower = future_prices[future_prices <= lower_barrier]

        if not hits_upper.empty and (hits_lower.empty or hits_upper.index[0] < hits_lower.index[0]):
            labels.iloc[i] = 1
        elif not hits_lower.empty and (hits_upper.empty or hits_lower.index[0] < hits_upper.index[0]):
            labels.iloc[i] = -1
        else:
            labels.iloc[i] = 0

    df["label"] = labels
    return df


if __name__ == "__main__":
    # Test with dummy data or load the downloaded EURUSD data
    try:
        data = pd.read_parquet("data/raw/EURUSD_1d.parquet")
        print(f"Loaded {len(data)} rows for labeling.")

        # Apply labels
        labeled_data = apply_triple_barrier(data, pt_sl=[2, 2], vertical_barrier=10)

        print("\nLabel Distribution:")
        print(labeled_data["label"].value_counts(normalize=True))

        # Save labeled data
        labeled_data.to_parquet("data/processed/EURUSD_labeled.parquet")
        print("\nSaved labeled data to data/processed/EURUSD_labeled.parquet")
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Test failed: {e}")
