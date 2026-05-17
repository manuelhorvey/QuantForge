import pandas as pd
import numpy as np
from models.hybrid_ensemble import HybridRegimeEnsemble
from signals.signal_generator import RegimeAwareSignalGenerator


def threshold_sweep(probs, prices, spread_bps=1.5,
                    thresholds=np.arange(0.45, 0.80, 0.025)):
    results = []
    n = len(probs)
    for thresh in thresholds:
        long_mask  = probs[:, 2] > thresh
        short_mask = probs[:, 0] > thresh

        n_long   = int(long_mask.sum())
        n_short  = int(short_mask.sum())
        n_trades = n_long + n_short

        if n_trades < 20:
            continue

        pnl = []
        for i in range(n - 1):
            if long_mask[i]:
                ret = (prices.iloc[i+1] / prices.iloc[i] - 1) - spread_bps / 10000
                pnl.append(ret)
            elif short_mask[i]:
                ret = -(prices.iloc[i+1] / prices.iloc[i] - 1) - spread_bps / 10000
                pnl.append(ret)

        pnl = np.array(pnl)
        if len(pnl) < 10:
            continue
        wins   = pnl[pnl > 0]
        losses = pnl[pnl < 0]

        expectancy   = pnl.mean()
        pf           = wins.sum() / (abs(losses.sum()) + 1e-9)
        win_rate     = (pnl > 0).mean()
        sharpe       = (pnl.mean() / (pnl.std() + 1e-9)) * np.sqrt(252)

        results.append({
            'threshold':  round(thresh, 3),
            'n_trades':   n_trades,
            'n_long':     n_long,
            'n_short':    n_short,
            'expectancy': round(expectancy, 6),
            'pf':         round(pf, 3),
            'win_rate':   round(win_rate, 3),
            'sharpe':     round(sharpe, 3),
        })

    return pd.DataFrame(results).sort_values('pf', ascending=False)


VAL_PERIOD  = ('2021-01-01', '2022-06-30')
TRAIN_UNTIL = '2020-12-31'


if __name__ == "__main__":
    print("Loading data...")
    base = pd.read_parquet("data/processed/EURUSD_features.parquet")
    regime_meta = pd.read_parquet("data/processed/EURUSD_regime_labels.parquet")
    struct = pd.read_parquet("data/processed/EURUSD_structural_features.parquet")
    interact = pd.read_parquet("data/processed/EURUSD_interaction_features.parquet")
    labeled = pd.read_parquet("data/processed/EURUSD_labeled.parquet")
    macro = pd.read_parquet("data/processed/macro_features.parquet")
    data = pd.read_parquet("data/raw/EURUSD_1d.parquet")

    common = base.index.intersection(regime_meta.index).intersection(
        struct.index).intersection(interact.index).intersection(labeled.index)

    macro_daily = macro.reindex(common, method='ffill')
    macro_daily.index = macro_daily.index.normalize()

    X = pd.concat([
        base.loc[common].drop('label', axis=1),
        regime_meta.loc[common][['P_trend', 'P_range', 'P_volatile', 'regime_confidence']],
        struct.loc[common],
        interact.loc[common],
        macro_daily[['rate_diff', 'rate_diff_delta_3m', 'real_yield_10y',
                     'yield_slope', 'dxy_mom_21', 'dxy_mom_63', 'fed_funds_delta_3m']]
    ], axis=1)

    y = (labeled.loc[common, 'label'] + 1).astype(int)
    regimes = regime_meta.loc[common, 'regime']
    regime_features = regime_meta.loc[common]

    train_mask = X.index <= TRAIN_UNTIL
    val_mask = (X.index >= VAL_PERIOD[0]) & (X.index <= VAL_PERIOD[1])

    X_train, y_train, r_train = X[train_mask], y[train_mask], regimes[train_mask]
    X_val = X[val_mask]
    regime_features_val = regime_features.loc[X_val.index]

    print(f"Train: {X_train.shape[0]} rows (up to {TRAIN_UNTIL})")
    print(f"Val:   {X_val.shape[0]} rows ({VAL_PERIOD[0]} to {VAL_PERIOD[1]})")

    ensemble = HybridRegimeEnsemble()
    ensemble.train(X_train, y_train, r_train)

    generator = RegimeAwareSignalGenerator(ensemble)
    signals = generator.generate_signals(X_val, regime_features_val)

    probs = signals[['raw_prob_short', 'raw_prob_neutral', 'raw_prob_long']].values
    prices = data['close'].reindex(signals.index)

    print("\nRunning threshold sweep on validation period...")
    results = threshold_sweep(probs, prices)

    print("\n" + "="*60)
    print("  THRESHOLD SWEEP RESULTS (validation: 2021-01 to 2022-06)")
    print("="*60)
    print(f"{'thresh':>7s} {'trades':>7s} {'long':>5s} {'short':>6s} {'exp':>10s} {'PF':>6s} {'WR':>5s} {'sharpe':>7s}")
    print("-"*55)
    for _, row in results.iterrows():
        print(f"{row['threshold']:>7.3f} {row['n_trades']:>7d} {row['n_long']:>5d} "
              f"{row['n_short']:>6d} {row['expectancy']:>+10.6f} {row['pf']:>6.3f} "
              f"{row['win_rate']:>5.3f} {row['sharpe']:>+7.3f}")

    # Find optimal: highest PF with n_trades >= 30
    valid = results[results['n_trades'] >= 30].reset_index(drop=True)
    if not valid.empty:
        best_idx = valid['pf'].idxmax()
        best = valid.loc[best_idx]
        print(f"\n{'='*60}")
        print(f"  OPTIMAL THRESHOLD: {best['threshold']:.3f}")
        print(f"    Trades: {best['n_trades']} (long={best['n_long']} short={best['n_short']})")
        print(f"    PF: {best['pf']:.3f}  Expectancy: {best['expectancy']:+.6f}")
        print(f"    Sharpe: {best['sharpe']:.3f}  Win rate: {best['win_rate']:.1%}")
        print(f"{'='*60}")

        # Show plateau around optimal
        print(f"\n  Plateau around optimal:")
        nearby = results[(results['threshold'] >= best['threshold'] - 0.05) &
                         (results['threshold'] <= best['threshold'] + 0.05)]
        for _, row in nearby.iterrows():
            marker = " <<<" if row['threshold'] == best['threshold'] else ""
            print(f"    {row['threshold']:.3f}  trades={row['n_trades']:3d}  "
                  f"PF={row['pf']:.3f}  exp={row['expectancy']:+.6f}{marker}")
    else:
        print("\nNo valid threshold found with >= 30 trades.")
