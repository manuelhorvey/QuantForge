import pandas as pd
import numpy as np
import xgboost as xgb
import yfinance as yf
from labels.triple_barrier import apply_triple_barrier
from features.publication_lags import apply_publication_lags

XLF_FEATURES = [
    'rate_diff',
    '2y_yield_delta_63',
    'xlf_mom_63',
    'xlf_vs_spy_63',
]

WF_CONFIG = {
    'train_years': 5,
    'test_years': 1,
    'step_years': 1,
    'min_trades': 20,
}




def fetch_data(start='2014-01-01', end='2026-12-31'):
    xlf = yf.download('XLF', start=start, end=end, auto_adjust=True)
    spy = yf.download('SPY', start=start, end=end, auto_adjust=True)
    for df in (xlf, spy):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
    xlf = xlf.rename(columns={'Close':'close','High':'high','Low':'low','Open':'open','Volume':'volume'})
    spy = spy.rename(columns={'Close':'close','High':'high','Low':'low','Open':'open','Volume':'volume'})
    xlf.index = pd.to_datetime(xlf.index).tz_localize('Europe/London')
    spy.index = pd.to_datetime(spy.index).tz_localize('Europe/London')
    return xlf, spy


def build_features(xlf, spy):
    m = pd.read_parquet('data/processed/macro_factors.parquet')
    m = apply_publication_lags(m)
    m = m.reindex(pd.date_range(m.index.min(), m.index.max(), freq='D')).ffill()
    m['rate_diff'] = m['fed_funds'] - m['ecb_rate']
    m['2y_yield_delta_63'] = m['us_2y'].diff(63)
    m = m.iloc[90:]  # drop diff-NaN rows

    labeled = apply_triple_barrier(xlf, pt_sl=[2, 2], vertical_barrier=20)

    pi = labeled.index.tz_localize(None)
    a = m.reindex(pi, method='ffill')
    a.index = labeled.index

    a['xlf_mom_63'] = xlf['close'].pct_change(63)
    a['xlf_vs_spy_63'] = a['xlf_mom_63'] - spy['close'].pct_change(63)

    clean = a.dropna(subset=XLF_FEATURES)
    clean['label'] = (labeled.loc[clean.index, 'label'] + 1).astype(int)
    return clean


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
    return {
        'n_trades': n_trades,
        'expectancy': expectancy,
        'pf': pf,
        'sharpe': sharpe,
    }


def run_walk_forward():
    print('Fetching data...')
    xlf, spy = fetch_data()
    print(f'XLF: {len(xlf)} rows  SPY: {len(spy)} rows')

    print('Building features...')
    data = build_features(xlf, spy)
    print(f'Clean data: {len(data)} rows ({data.index[0].date()} to {data.index[-1].date()})')

    years = sorted(data.index.year.unique())
    test_years = [y for y in years if y >= 2018 and y <= 2024]
    windows = []
    for ty in test_years:
        tr_end = ty - 1
        tr_start = tr_end - WF_CONFIG['train_years'] + 1
        windows.append((
            str(ty),
            f'{tr_start}-01-01', f'{tr_end}-12-31',
            f'{ty}-01-01', f'{ty}-12-31',
        ))

    results = []
    for label, tr_s, tr_e, te_s, te_e in windows:
        train_mask = (data.index >= tr_s) & (data.index <= tr_e)
        test_mask = (data.index >= te_s) & (data.index <= te_e)
        X_train = data.loc[train_mask, XLF_FEATURES]
        y_train = data.loc[train_mask, 'label'].astype(int)
        X_test = data.loc[test_mask, XLF_FEATURES]
        y_test = data.loc[test_mask, 'label'].astype(int)

        if len(X_train) < 100 or len(X_test) < 50:
            print(f'  {label}: insufficient data')
            continue

        proba, preds = run_window(X_train, y_train, X_test)
        trade_rets = simulate_trades(proba, preds, xlf['close'].reindex(X_test.index))

        metrics = compute_metrics(trade_rets)
        metrics['year'] = label
        metrics['train_rows'] = len(X_train)
        metrics['test_rows'] = len(X_test)
        metrics['n_long'] = int((preds == 2).sum())
        metrics['n_short'] = int((preds == 0).sum())
        results.append(metrics)

        if metrics['expectancy'] is None:
            print(f'  {label}: {metrics["n_trades"]} trades — insufficient for evaluation')
        else:
            print(f'  {label}: exp={metrics["expectancy"]:.6f}  PF={metrics["pf"]:.2f}  '
                  f'Sharpe={metrics["sharpe"]:.2f}  trades={metrics["n_trades"]}  '
                  f'L={metrics["n_long"]} S={metrics["n_short"]}')

        # Bootstrap test for key windows
        if metrics['expectancy'] is not None and label in ('2022', '2023', '2024'):
            trades_vals = trade_rets[trade_rets != 0].values
            if len(trades_vals) >= 20:
                pf_boot = []
                for _ in range(1000):
                    b = np.random.choice(trades_vals, size=len(trades_vals), replace=True)
                    spf = b[b>0].sum()/abs(b[b<0].sum()) if (b<0).any() else float('inf')
                    pf_boot.append(spf)
                pf_boot = np.array(pf_boot)
                p_pf = (pf_boot < 1.0).mean()
                sig = 'SIGNAL' if p_pf < 0.05 else ('BORDERLINE' if p_pf < 0.10 else 'noise')
                ci = np.percentile(pf_boot, [5, 95])
                print(f'         bootstrap p(PF<1.0)={p_pf:.3f} {sig}  CI=[{ci[0]:.2f}, {ci[1]:.2f}]')

    # Summary
    print('\n' + '=' * 60)
    print('WALK-FORWARD RESULTS — XLF Macro+Price (4 features)')
    print('=' * 60)
    header = f'{"Year":>6s}  {"Exp":>10s}  {"PF":>6s}  {"Sharpe":>7s}  {"Trades":>7s}  {"L/S":>6s}  {"Train":>6s}  {"Test":>5s}'
    print(header)
    print('-' * len(header))
    passed_2022 = False
    passed_2023 = False
    positive_windows = 0
    for r in results:
        exp_str = f'{r["expectancy"]:.6f}' if r['expectancy'] is not None else '  N/A  '
        pf_str = f'{r["pf"]:.2f}' if r['pf'] is not None else ' N/A '
        sharpe_str = f'{r["sharpe"]:.2f}' if r['sharpe'] is not None else '  N/A '
        ls = f'{r["n_long"]}/{r["n_short"]}' if r['n_long'] + r['n_short'] > 0 else '0/0'
        print(f'{r["year"]:>6s}  {exp_str:>10s}  {pf_str:>6s}  {sharpe_str:>7s}  '
              f'{r["n_trades"]:>7d}  {ls:>6s}  {r["train_rows"]:>6d}  {r["test_rows"]:>5d}')
        if r['expectancy'] is not None and r['expectancy'] > 0:
            positive_windows += 1
        if r['year'] == '2022' and r['expectancy'] is not None and r['expectancy'] > 0:
            passed_2022 = True
        if r['year'] == '2023' and r['expectancy'] is not None and r['expectancy'] > 0:
            passed_2023 = True

    print(f'\nGates:')
    print(f'  Positive exp in 2022: {"PASS" if passed_2022 else "FAIL"}')
    print(f'  Positive exp in 2023: {"PASS" if passed_2023 else "FAIL"}')
    print(f'  Positive windows ({positive_windows}/{len(results)} >= 5): {"PASS" if positive_windows >= 5 else "FAIL"}')
    low_pf = any(r['pf'] is not None and r['pf'] < 0.70 for r in results)
    print(f'  No PF < 0.70: {"FAIL" if low_pf else "PASS"}')
    low_trades = any(r['n_trades'] < 20 for r in results)
    print(f'  Min 20 trades/win: {"FAIL" if low_trades else "PASS"}')

    if passed_2022 and passed_2023 and positive_windows >= 5 and not low_pf and not low_trades:
        print('\n  >>> ALL GATES PASSED. PROCEED TO QQQ. <<<')
    else:
        print('\n  >>> GATES NOT MET. Review results. <<<')

    return results


if __name__ == '__main__':
    results = run_walk_forward()
