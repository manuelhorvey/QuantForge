# ADR-022: Macro Expert Head Adaptive Weighting

## Status
Accepted

## Context
The Hybrid Regime Ensemble uses a Macro Expert Head to provide a "fundamental" or "regime-based" overlay that is less susceptible to price-action noise. Currently, this head has a fixed blend weight (default 0.45). However, the relative predictive power of macro factors vs. price-based features fluctuates across different market regimes. A fixed weight may be sub-optimal during periods where macro drivers are either dominant or decoupled from price action.

## Decision
We will implement an adaptive weighting mechanism for the Macro Expert Head. This mechanism will:
1.  **Track Performance**: Maintain a rolling history of performance (returns) for both the Macro Expert Head and the blended model.
2.  **Relative Sharpe Update**: Periodically (or on every trade close) compare the 63-day rolling Sharpe ratio of the macro-only signals vs. the blended signals.
3.  **Soft Update Logic**: Adjust the blend weight `w` using a soft update: `w += 0.01 * (macro_sharpe - blend_sharpe)`.
4.  **Guardrails**: Constrain the weight within a strictly defined interval `[0.25, 0.65]` to prevent the model from becoming entirely dependent on macro or entirely ignoring it.

## Consequences
- **Improved Adaptivity**: The model can automatically increase macro reliance during fundamental-driven regimes (e.g., central bank pivot cycles) and decrease it when macro signal-to-noise is low.
- **Complexity**: Adds statefulness to the inference engine (AssetEngine needs to track and persist the current weight).
- **Inertia**: The soft update and rolling window provide stability, preventing erratic weight swings.
- **Monitoring**: The current macro weight becomes a key diagnostic metric for understanding model state.
