import pandas as pd
import numpy as np
import xgboost as xgb
import yfinance as yf
from pathlib import Path
from labels.triple_barrier import apply_triple_barrier, get_volatility

MACRO_FEATURES = [
    'yield_slope',
    'real_yield_10y',
    'rate_diff',
    'rate_diff_delta_3m',
    'dxy_mom_21',
    'fed_funds_delta_3m',
]

FEATURE_ALIASES = {
    'yield_slope': 'Yield Curve (2s10s)',
    'real_yield_10y': 'Real Yield 10y',
    'rate_diff': 'Rate Diff (US - ECB)',
    'rate_diff_delta_3m': 'Rate Diff Δ 3m',
    'dxy_mom_21': 'DXY Momentum 21d',
    'fed_funds_delta_3m': 'Fed Funds Δ 3m',
}

TRAIN_START = '2017-08-04'
TRAIN_END = '2022-08-04'
TEST_START = '2022-11-04'
TEST_END = '2024-12-31'


def fetch_xlf(start='2016-01-01', end='2026-12-31'):
    raw = yf.download('XLF', start=start, end=end, auto_adjust=True)
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={
        'Close': 'close', 'High': 'high',
        'Low': 'low', 'Open': 'open', 'Volume': 'volume',
    })
    if not hasattr(df.index, 'tz') or df.index.tz is None:
        df.index = pd.to_datetime(df.index).tz_localize('Europe/London')
    return df


def load_macro_features(price_index: pd.DatetimeIndex):
    raw = pd.read_parquet('data/processed/macro_factors.parquet')
    raw = raw.reindex(
        pd.date_range(raw.index.min(), raw.index.max(), freq='D')
    ).ffill()

    raw['rate_diff'] = raw['fed_funds'] - raw['ecb_rate']
    raw['yield_slope'] = raw['us_10y'] - raw['us_2y']
    raw['dxy_mom_21'] = raw['dxy'].pct_change(21)
    raw['fed_funds_delta_3m'] = raw['fed_funds'].diff(90)
    raw['rate_diff_delta_3m'] = raw['rate_diff'].diff(90)

    pi = price_index.tz_localize(None) if hasattr(price_index, 'tz') and price_index.tz is not None else price_index
    aligned = raw.reindex(pi, method='ffill')
    aligned.index = price_index
    return aligned


def run_diagnostic():
    print('=' * 60)
    print('XLF Macro-Only Diagnostic — 2022 to 2024')
    print('=' * 60)

    xlf = fetch_xlf()
    print(f'XLF: {len(xlf)} rows, {xlf.index[0].date()} to {xlf.index[-1].date()}')
    labeled = apply_triple_barrier(xlf, pt_sl=[2, 2], vertical_barrier=20)
    lb_dist = labeled['label'].value_counts(normalize=True).sort_index()
    print(f'Labels:  -1={lb_dist.get(-1,0):.0%}   0={lb_dist.get(0,0):.0%}   1={lb_dist.get(1,0):.0%}')

    macro = load_macro_features(labeled.index)
    common = macro.dropna(subset=MACRO_FEATURES).index
    X = macro.loc[common, MACRO_FEATURES]
    y = (labeled.loc[common, 'label'] + 1).astype(int)

    train_mask = (X.index >= TRAIN_START) & (X.index <= TRAIN_END)
    test_mask = (X.index >= TEST_START) & (X.index <= TEST_END)
    X_train, y_train = X[train_mask].dropna(), y[train_mask]
    X_test, y_test = X[test_mask].dropna(), y[test_mask]
    X_test = X_test.loc[X_test.index.intersection(y_test.index)]
    y_test = y_test.loc[X_test.index]

    print(f'\nTrain: {len(X_train)} rows, {sorted(y_train.unique())} labels')
    print(f'Test:  {len(X_test)} rows, {sorted(y_test.unique())} labels')

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=2,
        learning_rate=0.02,
        objective='multi:softprob',
        num_class=3,
        random_state=42,
        n_jobs=1,
        tree_method='hist',
        verbosity=0,
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)
    preds = model.predict(X_test)

    p_short = proba[:, 0]
    p_long = proba[:, 2]
    max_conf = np.maximum(p_short, p_long)

    n_long = int((preds == 2).sum())
    n_short = int((preds == 0).sum())
    n_neutral = int((preds == 1).sum())
    ls_ratio = n_long / max(n_short, 1)

    print(f'\n{" Metric":25s} {"Value":>10s}')
    print('-' * 36)
    print(f'{"P(short) mean":25s} {p_short.mean():>10.4f}')
    print(f'{"P(long) mean":25s} {p_long.mean():>10.4f}')
    print(f'{"Max confidence":25s} {max_conf.max():>10.4f}')
    print(f'{"Mean confidence":25s} {max_conf.mean():>10.4f}')
    print(f'{"Over 0.55":25s} {(max_conf > 0.55).sum():>4d}/{len(max_conf):<6d}')
    print(f'{"Over 0.50":25s} {(max_conf > 0.50).sum():>4d}/{len(max_conf):<6d}')
    print(f'{"Pred long":25s} {n_long:>10d}')
    print(f'{"Pred short":25s} {n_short:>10d}')
    print(f'{"Pred neutral":25s} {n_neutral:>10d}')
    print(f'{"L/S ratio":25s} {ls_ratio:>10.2f}')

    passed = (p_short.mean() > 0.50) and (max_conf.max() > 0.70)
    print(f'\n{"GATE: P(s)>0.50 & max_conf>0.70":30s} {"PASS" if passed else "FAIL":>6s}')

    print(f'\n--- Yearly Breakdown ---')
    df_y = pd.DataFrame({'ps': p_short, 'pl': p_long, 'pred': preds}, index=X_test.index)
    for yr in sorted(df_y.index.year.unique()):
        yd = df_y[df_y.index.year == yr]
        dl = int((yd['pred'] == 2).sum())
        ds = int((yd['pred'] == 0).sum())
        print(f'  {yr}: P(s)={yd["ps"].mean():.4f}  P(l)={yd["pl"].mean():.4f}  '
              f'L={dl:>3d}  S={ds:>3d}  L/S={dl/max(ds,1):.2f}')

    print(f'\n--- Feature Importance ---')
    imp = pd.DataFrame({
        'feature': MACRO_FEATURES,
        'importance': model.feature_importances_,
        'alias': [FEATURE_ALIASES[f] for f in MACRO_FEATURES],
    }).sort_values('importance', ascending=False)
    for _, r in imp.iterrows():
        print(f'  {r["alias"]:30s} {r["importance"]:.3f}')

    print(f'\n--- Correlation: Macro Features vs XLF Daily Returns ---')
    xlf_ret = xlf['close'].pct_change().reindex(X_test.index)
    for col in MACRO_FEATURES:
        corr = X_test[col].corr(xlf_ret)
        print(f'  {FEATURE_ALIASES[col]:30s} {corr:+.4f}')

    print(f'\n--- Signal Direction Check (2022 only) ---')
    y2022 = df_y[df_y.index.year == 2022]
    xlf_2022 = xlf.loc[y2022.index]
    xlf_2022_ret = xlf_2022['close'].pct_change().sum()
    print(f'  2022 XLF return: {xlf_2022_ret:+.2%}')

    xlf_2024 = xlf.loc[df_y[df_y.index.year == 2024].index]
    xlf_2024_ret = xlf_2024['close'].pct_change().sum()
    print(f'  2024 XLF return: {xlf_2024_ret:+.2%}')
    print(f'  2024 P(short)={y2022["ps"].mean():.4f} vs actual={xlf_2024_ret:+.2%}')

    print(f'\n=== Conclusion ===')
    if passed:
        print('  Gate passed. Signal confirmed in clean code. Proceed to walk-forward.')
    else:
        print('  Gate failed. Do not proceed. Investigate filter or feature adjustments.')

    return {'model': model, 'X_test': X_test, 'y_test': y_test, 'proba': proba, 'preds': preds}


if __name__ == '__main__':
    run_diagnostic()
