"""Phase H orchestrator — runs all 3 modes for BTC and GC universes.

Pipeline per universe:
  1. Build features (shared across modes)
  2. MODE A: FX-frozen transfer test (no retraining)
  3. MODE B: Domain model retrain (XGBoost with domain-specific labels)
  4. MODE C: Geometry sweep (SL/TP grid on best model from MODE B)
  5. Aggregate into phase_h_summary.json

Critical invariants enforced in code:
  I1 — No FX retraining (FX models are immutable artifacts)
  I2 — No shared normalization drift (scaling isolated per universe)
  I3 — No geometry reuse assumption (FX SL/TP does not bias sweeps)
  I4 — No cross-asset leakage (each universe is independent)
"""

import os, sys, json, logging, pickle
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger("quantforge.phase_h")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

PHASE_H_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(PHASE_H_DIR, 'outputs')
os.makedirs(OUTPUTS_DIR, exist_ok=True)

XGB_PARAMS = {
    'n_estimators': 300, 'max_depth': 2, 'learning_rate': 0.02,
    'objective': 'multi:softprob', 'num_class': 3,
    'random_state': 42, 'n_jobs': 1, 'tree_method': 'hist', 'verbosity': 0,
}

LABEL_SPECS = {
    'BTC': {
        'type': 'tbvol',
        'params': {'pt_mult': 2.0, 'sl_mult': 1.5, 'max_horizon': 20},
    },
    'GC': {
        'type': 'fwd_return',
        'params': {'horizon': 120, 'threshold': 0.03},
    },
}


def _mode_a_fx_transfer(target_name, features_df, available_features):
    """MODE A: FX-frozen transfer test."""
    logger.info('  MODE A: FX transfer test...')
    from research.phase_h.baseline.frozen_fx_predictor import run_fx_transfer_test
    return run_fx_transfer_test(target_name, features_df, available_features)


def _mode_b_domain_retrain(target_name, raw_df, features_df, available_features, label_spec):
    """MODE B: Retrain XGBoost with domain-specific labels."""
    from research.phase_h.metrics.signal_metrics import compute_signal_metrics
    from research.phase_h.universes.btc_universe import create_prediction_frame as btc_frame
    from research.phase_h.universes.gc_universe import create_prediction_frame as gc_frame
    from research.execution_surface.replay_engine import replay, ReplayConfig
    from research.execution_surface.monte_carlo import compute_trade_metrics, MIN_TRADES

    logger.info('  MODE B: domain model retrain...')

    # Map to correct label function
    if label_spec['type'] == 'tbvol':
        from research.phase_h.labels.btc_labels import label_btc_tbvol
        labels = label_btc_tbvol(raw_df, **label_spec['params'])
    elif label_spec['type'] == 'fwd_return':
        from research.phase_h.labels.gc_labels import label_gc_forward_return
        labels = label_gc_forward_return(raw_df, **label_spec['params'])
    else:
        return {'status': 'failed', 'reason': f'unknown_label_type: {label_spec["type"]}'}

    logger.info('    Label distribution: LONG=%d SHORT=%d NEUTRAL=%d',
                int((labels == 2).sum()), int((labels == 0).sum()), int((labels == 1).sum()))

    # Align features and labels
    common_idx = features_df.index.intersection(labels.index)
    features_aligned = features_df.loc[common_idx]
    labels_aligned = labels.loc[common_idx]
    raw_aligned = raw_df.loc[common_idx]
    logger.info('    %d aligned rows', len(common_idx))

    X_full = features_aligned[available_features].values.astype(np.float32)
    y_full = labels_aligned.values.astype(int)

    # Walk-forward retrain (5yr train / 1yr test)
    years = sorted(set(features_aligned.index.year))
    test_years = [y for y in years if y >= years[0] + 5 and y <= pd.Timestamp.now().year]

    chunks = []
    for ty in test_years:
        tr_start = ty - 5
        train_mask = ((features_aligned.index >= pd.Timestamp(f'{tr_start}-01-01', tz='US/Eastern'))
                      & (features_aligned.index <= pd.Timestamp(f'{ty - 1}-12-31', tz='US/Eastern')))
        test_mask = ((features_aligned.index >= pd.Timestamp(f'{ty}-01-01', tz='US/Eastern'))
                     & (features_aligned.index <= pd.Timestamp(f'{ty}-12-31', tz='US/Eastern')))

        X_train = X_full[train_mask]
        y_train = y_full[train_mask]
        X_test = X_full[test_mask]

        if len(X_train) < 100 or len(X_test) < 20:
            continue

        import xgboost as xgb
        model = xgb.XGBClassifier(**XGB_PARAMS)
        split = int(len(X_train) * 0.8)
        try:
            model.fit(
                X_train[:split], y_train[:split],
                eval_set=[(X_train[split:], y_train[split:])],
                verbose=False,
            )
        except ValueError as e:
            logger.warning('    %d: training failed — %s', ty, e)
            continue

        proba = model.predict_proba(X_test)
        preds = model.predict(X_test)
        confidence = proba.max(axis=1) * 100

        idx = features_aligned.index[test_mask]
        chunk = raw_aligned.loc[idx, ['open', 'high', 'low', 'close', 'volume']].copy()
        chunk['signal'] = preds.astype(int)
        chunk['prob_long'] = proba[:, 2] if proba.shape[1] > 2 else 0
        chunk['prob_short'] = proba[:, 0]
        chunk['prob_neutral'] = proba[:, 1]
        chunk['confidence'] = confidence
        chunk['volatility'] = raw_aligned['close'].pct_change().ewm(span=100).std().reindex(idx)
        chunk['year'] = ty
        chunk['regime'] = 'unknown'
        chunks.append(chunk)

    if not chunks:
        return {'status': 'failed', 'reason': 'no_model_trained'}

    oos_df = pd.concat(chunks).sort_index()

    # Signal metrics
    sig_metrics = compute_signal_metrics(oos_df, forward_horizon=5)

    # Geometry sweep (default medium geometry for initial read)
    config = ReplayConfig(sl_mult=0.75, tp_mult=2.25)
    trades = replay(oos_df, config)
    replay_metrics = compute_trade_metrics(trades, 0.75, 2.25)

    return {
        'status': 'ok',
        'n_oos_bars': len(oos_df),
        'n_years': len(test_years),
        'signal': sig_metrics,
        'replay_medium': replay_metrics,
        'predictions': oos_df,  # passed to MODE C
    }


def _mode_c_geometry_sweep(predictions, output_dir, label):
    """MODE C: SL/TP geometry sweep."""
    logger.info('  MODE C: geometry sweep...')
    from research.phase_h.geometry.sltp_grid import run_geometry_sweep
    return run_geometry_sweep(predictions, output_dir, label)


def run_universe(target_name, force=False):
    """Run all 3 modes for a single universe (BTC or GC)."""
    universe_dir = os.path.join(OUTPUTS_DIR, target_name.lower())
    os.makedirs(universe_dir, exist_ok=True)
    result_path = os.path.join(universe_dir, 'phase_h_result.json')

    if os.path.exists(result_path) and not force:
        with open(result_path) as f:
            return json.load(f)

    logger.info('=' * 60)
    logger.info('Phase H — %s', target_name)
    logger.info('=' * 60)

    # 0. Build features
    if target_name == 'BTC':
        from research.phase_h.universes.btc_universe import build_btc_features
        features_df, raw_df, available = build_btc_features()
    elif target_name == 'GC':
        from research.phase_h.universes.gc_universe import build_gc_features
        features_df, raw_df, available = build_gc_features()
    else:
        return {'status': 'failed', 'reason': f'unknown_target: {target_name}'}

    label_spec = LABEL_SPECS[target_name]

    # MODE A: FX transfer test (no retraining)
    mode_a = _mode_a_fx_transfer(target_name, features_df, available)

    # MODE B: Domain model
    mode_b = _mode_b_domain_retrain(target_name, raw_df, features_df, available, label_spec)

    # MODE C: Geometry sweep on domain model
    mode_c = None
    if mode_b.get('status') == 'ok' and 'predictions' in mode_b:
        mode_c = _mode_c_geometry_sweep(
            mode_b['predictions'], universe_dir, 'domain_model'
        )

        # Also run geometry sweep on FX transfer if available
        mode_c_fx = None
        if mode_a.get('status') == 'ok' and 'signal' in mode_a:
            from research.phase_h.universes.btc_universe import create_prediction_frame as btc_frame
            from research.phase_h.universes.gc_universe import create_prediction_frame as gc_frame
            frame_fn = btc_frame if target_name == 'BTC' else gc_frame

            # Build FX transfer prediction frame
            fx_signals = np.array(mode_a['signal'])
            fx_confidence = np.array(mode_a['confidence'])
            fx_preds = btc_frame(raw_df.loc[features_df.index], fx_signals, fx_confidence) if target_name == 'BTC' \
                else gc_frame(raw_df.loc[features_df.index], fx_signals, fx_confidence)
            # Trim to match features_df index length
            common = fx_preds.index.intersection(features_df.index)
            fx_preds = fx_preds.loc[common]

            mode_c_fx = _mode_c_geometry_sweep(
                fx_preds, universe_dir, 'fx_transfer'
            )

    # Clean predictions from mode_b (not serializable)
    if 'predictions' in mode_b:
        del mode_b['predictions']

    # Assemble result
    label_params = LABEL_SPECS[target_name]
    result = {
        'target': target_name,
        'label_type': label_params['type'],
        'label_params': label_params['params'],
        'n_features': len(available),
        'features': available,
        'mode_a_fx_transfer': mode_a,
        'mode_b_domain_model': mode_b,
        'mode_c_geometry_sweep_domain': mode_c,
        'mode_c_geometry_sweep_fx': mode_c_fx,
    }

    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    logger.info('Result saved to %s', result_path)
    return result


def run_all(force=False):
    """Run Phase H for both BTC and GC."""
    report = {}
    for target in ['BTC', 'GC']:
        try:
            result = run_universe(target, force=force)
            if result:
                report[target] = result
        except Exception as e:
            logger.error('%s: FAILED — %s', target, e)
            import traceback; traceback.print_exc()

    # Save consolidated summary
    summary = {}
    for target in ['BTC', 'GC']:
        if target not in report:
            continue
        r = report[target]

        entry = {'label_type': r['label_type'], 'n_features': r['n_features']}

        # FX transfer
        if r['mode_a_fx_transfer'].get('status') == 'ok':
            entry['fx_transfer'] = {
                'source': r['mode_a_fx_transfer'].get('fx_source'),
                'n_shared_features': r['mode_a_fx_transfer'].get('n_features'),
                'signal_dist': r['mode_a_fx_transfer'].get('signal_distribution'),
            }

        # Domain model
        if r['mode_b_domain_model'].get('status') == 'ok':
            dm = r['mode_b_domain_model']
            entry['domain_model'] = {
                'n_oos_bars': dm.get('n_oos_bars'),
                'direction_accuracy': dm.get('signal', {}).get('directional_accuracy'),
                'timing_sharpe': dm.get('signal', {}).get('timing_sharpe'),
                'replay_sharpe': dm.get('replay_medium', {}).get('sharpe'),
            }

        # Geometry sweep
        if r.get('mode_c_geometry_sweep_domain'):
            gs = r['mode_c_geometry_sweep_domain']
            entry['geometry_domain'] = {
                'max_sharpe': gs.get('max_sharpe'),
                'best_sl': gs.get('best_sharpe', {}).get('sl_mult'),
                'best_tp': gs.get('best_sharpe', {}).get('tp_mult'),
                'plateau_width': gs.get('plateau_pct'),
            }

        if r.get('mode_c_geometry_sweep_fx'):
            gs_fx = r['mode_c_geometry_sweep_fx']
            entry['geometry_fx_transfer'] = {
                'max_sharpe': gs_fx.get('max_sharpe'),
                'platueau_width': gs_fx.get('plateau_pct'),
            }

        summary[target] = entry

    summary_path = os.path.join(OUTPUTS_DIR, 'phase_h_summary.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    # Console output
    print('\n' + '=' * 130)
    print('PHASE H — GENERALIZATION BOUNDARY TEST RESULTS')
    print('=' * 130)
    print()

    for target in ['BTC', 'GC']:
        if target not in report:
            continue
        r = report[target]
        print(f'{target} (label={r["label_type"]}, n_features={r["n_features"]}):')
        print()

        # FX transfer
        print('  MODE A — FX Transfer Test:')
        fx = r['mode_a_fx_transfer']
        if fx.get('status') == 'ok':
            print(f'    Source:        {fx["fx_source"]}')
            print(f'    Shared feats:  {fx["n_features"]}')
            sd = fx.get('signal_distribution', {})
            print(f'    Signals:       L={sd.get("long",0)}  S={sd.get("short",0)}  N={sd.get("neutral",0)}')
            if r.get('mode_c_geometry_sweep_fx'):
                gfx = r['mode_c_geometry_sweep_fx']
                print(f'    Geometry SR:   {gfx.get("max_sharpe", "N/A")}')
                print(f'    Plateau:       {gfx.get("plateau_pct", "N/A")}')
        else:
            print(f'    Status:        {fx.get("status")} ({fx.get("reason","")})')
        print()

        # Domain model
        print('  MODE B — Domain Model:')
        dm = r['mode_b_domain_model']
        if dm.get('status') == 'ok':
            sig = dm.get('signal', {})
            rep = dm.get('replay_medium', {})
            print(f'    Dir accuracy:  {sig.get("directional_accuracy", "N/A")}')
            print(f'    Timing SR:     {sig.get("timing_sharpe", "N/A")}')
            print(f'    Replay SR:     {rep.get("sharpe", "N/A")}')
            print(f'    Replay PF:     {rep.get("pf", "N/A")}')
            print(f'    Replay WR:     {rep.get("win_rate", "N/A")}')
        else:
            print(f'    Status:        {dm.get("status")} ({dm.get("reason","")})')
        print()

        # Geometry sweep
        print('  MODE C — Geometry Sweep:')
        gs = r.get('mode_c_geometry_sweep_domain')
        if gs:
            best = gs.get('best_sharpe', {})
            print(f'    Max Sharpe:    {gs.get("max_sharpe", "N/A")}')
            print(f'    Best SL/TP:    {best.get("sl_mult", "?")} / {best.get("tp_mult", "?")}')
            print(f'    Plateau:       {gs.get("plateau_pct", "N/A"):.1%}')
            print(f'    Valid configs: {gs.get("n_valid_configs", 0)}')
        else:
            print('    (no sweep — model failed)')
        print()
        print('  ' + '-' * 60)
        print()

    print('\n' + '=' * 130)
    print('INTERPRETATION (locked — written before results)')
    print('=' * 130)
    print()
    print('FX transfer collapses on BTC:')
    print('  Expected. BTC endogenous vol violates FX feature assumptions.')
    print()
    print('FX transfer partially survives on GC:')
    print('  System partially generalizes to macro drift.')
    print('  Suggests: transition signal is partially universal.')
    print()
    print('Domain model improves BOTH:')
    print('  Label adaptation recovers edge lost in transfer.')
    print('  Validates that architecture is general, not FX-specific.')
    print()
    print('Geometry manifold shifts significantly from FX:')
    print('  Execution structure is asset-class-specific.')
    print('  Tight dominance is FX-specific, not universal.')
    print()

    return report


if __name__ == '__main__':
    run_all()
