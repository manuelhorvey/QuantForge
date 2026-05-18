# ADR-017: Inference path lookahead investigation

**Date:** 2026-05-18
**Status:** Investigated — no active bug

## Context

A codebase audit flagged `_build_features()` in `paper_trading/engine.py` as a lookahead bug. The method computes labels during both training **and** inference. During inference the label computation drops rows with incomplete future windows (e.g. `shift(-60)` for fwd60, `vertical_barrier=20` for tb20). This raised concern that the model was predicting on stale features from 20–60 days ago.

## Investigation

Added a diagnostic that runs `_build_features()` live and measures the gap between the last feature row date and today:

| Asset | Label scheme | Feature gap | Verdict |
|-------|-------------|-------------|---------|
| CADJPY | fwd60 | 0 days | Clean |
| GC | fwd60 | 3 days (weekend) | Clean |
| BTC | tb20 | 3 days (weekend) | Clean |
| NZDJPY | tb20 | 0 days | Clean |

## Why no staleness occurs

The dropped-row concern was correct in theory but does not manifest because:

- **fwd60** (`shift(-60)`): The lambda `2 if x > 0.02 else (0 if x < -0.02 else 1)` converts NaN to `1` (neutral). No rows dropped by `.dropna()`.
- **tb20** (`apply_triple_barrier`): Incomplete windows return `0` (neutral), not NaN. No rows dropped.
- The `label` column only affects `.dropna(subset=[features + 'label'])` filtering. Features are never computed from labels.

The model receives features from the latest available date for all assets.

## Risk

The pattern is structurally fragile. A future change to the label logic (e.g. changing the fwd60 lambda to `dropna()`, or switching to a different barrier implementation that returns NaN) would silently introduce stale feature inference. The live trade would degrade with no obvious error signal.

## Scheduled fix

January retrain cycle — extract `_build_inference_features()` that never computes labels. This closes the structural risk without affecting current results.

## Affected code

- `paper_trading/engine.py:160-200` — `AssetEngine._build_features()`
