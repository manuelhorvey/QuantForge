import pandas as pd
import ta


def generate_base_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generates baseline trend and mean reversion features.
    
    Args:
        df: DataFrame with ohlcv data
        
    Returns:
        pd.DataFrame: Data with features appended
    """
    df = df.copy()

    # --- Trend Features ---
    # EMA Spreads
    df['ema_20'] = ta.trend.ema_indicator(df['close'], window=20)
    df['ema_50'] = ta.trend.ema_indicator(df['close'], window=50)
    df['ema_spread'] = (df['ema_20'] - df['ema_50']) / df['ema_50']

    # ADX (Trend Strength)
    df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)

    # MACD
    macd = ta.trend.MACD(df['close'])
    df['macd_diff'] = macd.macd_diff()

    # --- Mean Reversion Features ---
    # RSI
    df['rsi'] = ta.momentum.rsi(df['close'], window=14)

    # Bollinger Bands Z-Score
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_mavg'] = bb.bollinger_mavg()
    df['bb_std'] = bb.bollinger_hband() - df['bb_mavg'] # Approx std
    df['bb_zscore'] = (df['close'] - df['bb_mavg']) / (df['bb_std'] / 2)

    # Distance from EMA 20
    df['dist_ema_20'] = (df['close'] - df['ema_20']) / df['ema_20']

    # --- Clean up ---
    # Features to keep
    feature_cols = [
        'ema_spread', 'adx', 'macd_diff',
        'rsi', 'bb_zscore', 'dist_ema_20'
    ]

    return df[feature_cols].dropna()

if __name__ == "__main__":
    try:
        data = pd.read_parquet("data/processed/EURUSD_labeled.parquet")
        features = generate_base_features(data)

        # Merge with labels
        final_df = features.join(data['label'], how='inner')

        print(f"Generated {len(features.columns)} features for {len(final_df)} rows.")
        print("\nFeatures Sample:")
        print(final_df.head())

        # Save to data/processed
        final_df.to_parquet("data/processed/EURUSD_features.parquet")
        print("\nSaved features to data/processed/EURUSD_features.parquet")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Feature generation failed: {e}")
