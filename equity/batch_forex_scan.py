import pandas as pd
import numpy as np
import xgboost as xgb
import yfinance as yf
import warnings
import sys
import json
import os
from datetime import datetime
from features.pair_specific import (
    build_nzdjpy_features,
    build_eurusd_features,
    build_usdjpy_features,
    build_gc_features,
)

warnings.filterwarnings('ignore')

TICKERS = [
    "EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCAD=X","NZDUSD=X","USDCHF=X",
    "EURGBP=X","EURJPY=X","GBPJPY=X","AUDJPY=X","CHFJPY=X","EURCHF=X","EURAUD=X",
    "GBPAUD=X","AUDCAD=X","NZDJPY=X","EURCAD=X","GBPCAD=X","AUDNZD=X","CADJPY=X",
    "EURNZD=X","GBPNZD=X","GBPCHF=X","CADCHF=X","NZDCAD=X","NZDCHF=X","AUDCHF=X",
    "GC=F","BTC-USD",
]

WF_CONFIG = {'train_years': 5, 'test_years': 1, 'step_years': 1, 'min_trades': 20}

RESULTS_DIR = 'data/scans'

SPECIAL_BUILDERS = {
    'NZDJPY=X': build_nzdjpy_features,
    'USDJPY=X': build_usdjpy_features,
    'GC=F': build_gc_features,
}

# Pre-fetched data shared across builders to avoid redundant downloads
_SHARED_DATA: dict[str, pd.DataFrame | None] = {}


def fetch_ticker(symbol, start='2014-01-01', end='2026-12-31'):
    try:
        df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.rename(columns={'Close': 'close', 'High': 'high', 'Low': 'low',
                                'Open': 'open', 'Volume': 'volume'})
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize('Europe/London')
        return df
    except Exception as e:
        return None


def load_macro():
    m = pd.read_parquet('data/processed/macro_factors.parquet')
    m = m.reindex(pd.date_range(m.index.min(), m.index.max(), freq='D')).ffill()
    m['rate_diff'] = m['fed_funds'] - m['ecb_rate']
    m = m.iloc[90:]
    return m


def make_generic_features(price, macro, symbol):
    from labels.triple_barrier import apply_triple_barrier
    labeled = apply_triple_barrier(price, pt_sl=[2, 2], vertical_barrier=20)
    pi = labeled.index.tz_localize(None) if hasattr(labeled.index, 'tz') and labeled.index.tz is not None else labeled.index
    a = macro.reindex(pi, method='ffill')
    a.index = labeled.index

    base = symbol.replace('=X', '').lower()

    a['dxy_mom_21'] = a['dxy'].pct_change(21)
    a['vix_ma21'] = a['vix'].rolling(21).mean()
    a['vix_delta_5'] = a['vix'].diff(5)

    a[f'{base}_mom_21'] = price['close'].pct_change(21)
    a[f'{base}_mom_63'] = price['close'].pct_change(63)

    features = ['rate_diff', 'dxy_mom_21', 'vix_ma21', f'{base}_mom_21']
    clean = a.dropna(subset=features)
    clean['label'] = (labeled.loc[clean.index, 'label'] + 1).astype(int)
    return clean, features


def make_btc_features(price, macro):
    from labels.triple_barrier import apply_triple_barrier
    labeled = apply_triple_barrier(price, pt_sl=[2, 2], vertical_barrier=20)
    pi = labeled.index.tz_localize(None) if hasattr(labeled.index, 'tz') and labeled.index.tz is not None else labeled.index
    a = macro.reindex(pi, method='ffill')
    a.index = labeled.index

    a['dxy_mom_21'] = a['dxy'].pct_change(21)
    a['vix_ma21'] = a['vix'].rolling(21).mean()
    a['vix_delta_5'] = a['vix'].diff(5)
    a['btc_mom_21'] = price['close'].pct_change(21)
    a['btc_mom_63'] = price['close'].pct_change(63)
    a['btc_vol_21'] = price['close'].pct_change().rolling(21).std()

    features = ['rate_diff', 'dxy_mom_21', 'vix_ma21', 'btc_mom_21', 'btc_mom_63', 'btc_vol_21']
    clean = a.dropna(subset=features)
    clean['label'] = (labeled.loc[clean.index, 'label'] + 1).astype(int)
    return clean, features


def run_window(X_train, y_train, X_test):
    model = xgb.XGBClassifier(
        n_estimators=300, max_depth=2, learning_rate=0.02,
        objective='multi:softprob', num_class=3,
        random_state=42, n_jobs=1, tree_method='hist', verbosity=0,
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)
    preds = model.predict(X_test)
    return proba, preds


def simulate_trades(proba, preds, prices):
    long_mask = preds == 2
    short_mask = preds == 0
    rets = prices.pct_change()
    trade_rets = pd.Series(0.0, index=prices.index)
    trade_rets[long_mask] = rets[long_mask]
    trade_rets[short_mask] = -rets[short_mask]
    return trade_rets


def compute_metrics(trade_rets):
    trades = trade_rets[trade_rets != 0]
    n_trades = len(trades)
    if n_trades < WF_CONFIG['min_trades']:
        return {'n_trades': n_trades, 'expectancy': None, 'pf': None, 'sharpe': None}
    expectancy = trades.mean()
    pf = trades[trades > 0].sum() / abs(trades[trades < 0].sum()) if (trades < 0).any() else float('inf')
    sharpe = trades.mean() / trades.std() * np.sqrt(252) if trades.std() > 0 else 0.0
    return {'n_trades': n_trades, 'expectancy': expectancy, 'pf': pf, 'sharpe': sharpe}


def run_single_ticker(symbol):
    print(f'\n{"="*60}')
    print(f'  {symbol}')
    print(f'{"="*60}')

    price = fetch_ticker(symbol)
    if price is None or len(price) < 500:
        print(f'  FAILED: insufficient data')
        return None

    print(f'  Rows: {len(price)}')

    macro = load_macro()

    if symbol == 'EURUSD=X':
        gc_price = _SHARED_DATA.get('GC=F')
        try:
            data, features = build_eurusd_features(price, macro, cot_weekly=None)
        except Exception as e:
            print(f'  FAILED: EURUSD builder error: {e}')
            return None
    elif symbol in SPECIAL_BUILDERS:
        builder = SPECIAL_BUILDERS[symbol]
        try:
            data, features = builder(price, macro)
        except Exception as e:
            print(f'  FAILED: special builder error: {e}')
            return None
    elif symbol == 'BTC-USD':
        try:
            data, features = make_btc_features(price, macro)
        except Exception as e:
            print(f'  FAILED: BTC builder error: {e}')
            return None
    else:
        try:
            data, features = make_generic_features(price, macro, symbol)
        except Exception as e:
            print(f'  FAILED: generic builder error: {e}')
            return None

    print(f'  Features: {features}')
    print(f'  Clean data: {len(data)} rows ({data.index[0].date()} to {data.index[-1].date()})')

    years = sorted(data.index.year.unique())
    test_years = [y for y in years if 2018 <= y <= 2024]

    results = []
    for ty in test_years:
        tr_end = ty - 1
        tr_start = tr_end - WF_CONFIG['train_years'] + 1
        train_mask = (data.index >= f'{tr_start}-01-01') & (data.index <= f'{tr_end}-12-31')
        test_mask = (data.index >= f'{ty}-01-01') & (data.index <= f'{ty}-12-31')
        X_train = data.loc[train_mask, features]
        y_train = data.loc[train_mask, 'label'].astype(int)
        X_test = data.loc[test_mask, features]
        if len(X_train) < 100 or len(X_test) < 50:
            continue

        proba, preds = run_window(X_train, y_train, X_test)
        trade_rets = simulate_trades(proba, preds, price['close'].reindex(X_test.index))
        metrics = compute_metrics(trade_rets)
        metrics['year'] = str(ty)
        metrics['train_rows'] = len(X_train)
        metrics['test_rows'] = len(X_test)
        metrics['n_long'] = int((preds == 2).sum())
        metrics['n_short'] = int((preds == 0).sum())
        results.append(metrics)

        if metrics['expectancy'] is None:
            print(f'    {ty}: {metrics["n_trades"]} trades — insufficient')
        else:
            print(f'    {ty}: exp={metrics["expectancy"]:.6f}  PF={metrics["pf"]:.2f}  '
                  f'Sharpe={metrics["sharpe"]:.2f}  trades={metrics["n_trades"]}  '
                  f'L={metrics["n_long"]} S={metrics["n_short"]}')

    if not results:
        print(f'  No valid windows')
        return None

    pos = sum(1 for r in results if r['expectancy'] is not None and r['expectancy'] > 0)
    avg_exp = np.mean([r['expectancy'] for r in results if r['expectancy'] is not None]) if any(r['expectancy'] is not None for r in results) else None
    avg_pf = np.mean([r['pf'] for r in results if r['pf'] is not None]) if any(r['pf'] is not None for r in results) else None
    avg_sharpe = np.mean([r['sharpe'] for r in results if r['sharpe'] is not None]) if any(r['sharpe'] is not None for r in results) else None

    summary = {
        'symbol': symbol,
        'windows': len(results),
        'positive': pos,
        'avg_exp': avg_exp,
        'avg_pf': avg_pf,
        'avg_sharpe': avg_sharpe,
        'pass_rate': f'{pos}/{len(results)}',
    }

    print(f'  ---> Positive: {pos}/{len(results)}  Avg Exp: {avg_exp:.6f}  Avg PF: {avg_pf:.2f}  Avg Sharpe: {avg_sharpe:.2f}')
    return summary


def _save_results(all_results: list[dict], scan_time: str):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    summary = {
        'scan_time': scan_time,
        'n_tickers': len(TICKERS),
        'n_success': len(all_results),
        'results': all_results,
    }
    json_path = os.path.join(RESULTS_DIR, f'batch_scan_{ts}.json')
    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f'\n  Results saved: {json_path}')


def main():
    print('=' * 60)
    print('  QUANTFORGE — BATCH FOREX/COMMODITY/CRYPTO SCAN')
    scan_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f'  Started: {scan_time}')
    print(f'  Tickers: {len(TICKERS)}')
    print('=' * 60)

    print('\nPre-fetching shared data (GC=F)...')
    gc_price = fetch_ticker('GC=F')
    _SHARED_DATA['GC=F'] = gc_price
    print(f'  GC=F: {len(gc_price) if gc_price is not None else 0} rows')

    all_results = []
    for i, ticker in enumerate(TICKERS, 1):
        print(f'\n[{i}/{len(TICKERS)}] ', end='')
        sys.stdout.flush()
        result = run_single_ticker(ticker)
        if result:
            all_results.append(result)

    print('\n\n' + '=' * 80)
    print('  BATCH RESULTS SUMMARY')
    print('=' * 80)
    header = f'{"Ticker":>12s}  {"Pass":>6s}  {"Avg Exp":>10s}  {"Avg PF":>6s}  {"Avg Sharpe":>7s}  {"Windows":>7s}'
    print(header)
    print('-' * len(header))

    ranked = sorted(all_results, key=lambda r: (r['positive'] / max(r['windows'], 1), r['avg_pf'] or 0), reverse=True)

    for r in ranked:
        exp_str = f'{r["avg_exp"]:.6f}' if r['avg_exp'] is not None else '   N/A  '
        pf_str = f'{r["avg_pf"]:.2f}' if r['avg_pf'] is not None else '  N/A '
        sharpe_str = f'{r["avg_sharpe"]:.2f}' if r['avg_sharpe'] is not None else '  N/A '
        print(f'{r["symbol"]:>12s}  {r["pass_rate"]:>6s}  {exp_str:>10s}  {pf_str:>6s}  {sharpe_str:>7s}  {r["windows"]:>7d}')

    print('-' * len(header))
    n_promising = sum(1 for r in ranked if r['positive'] >= 4 and r['avg_pf'] is not None and r['avg_pf'] >= 1.5)
    print(f'\nPromising (>=4/7 pos, PF>=1.5): {n_promising}/{len(ranked)}')
    for r in ranked:
        if r['positive'] >= 4 and r['avg_pf'] is not None and r['avg_pf'] >= 1.5:
            print(f'  >>> {r["symbol"]}: {r["pass_rate"]}  PF={r["avg_pf"]:.2f}  Sharpe={r["avg_sharpe"]:.2f}')

    _save_results(ranked, scan_time)


if __name__ == '__main__':
    main()
