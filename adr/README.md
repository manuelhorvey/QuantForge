# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for QuantForge.

ADRs document key architectural and design decisions, including context, options considered, and the chosen approach.

## Index

All ADRs live in [`docs/adr/`](../docs/adr/) unless noted.

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](../docs/adr/ADR-001-triple-barrier-labeling.md) | Triple Barrier Labeling | Accepted |
| [ADR-002](../docs/adr/ADR-002-regime-classifier-as-router.md) | Regime Classifier as Router | Accepted |
| [ADR-003](../docs/adr/ADR-003-expanding-train-window.md) | Expanding Train Window | Accepted |
| [ADR-004](../docs/adr/ADR-004-eurusd-rejected.md) | EURUSD Rejected | Accepted |
| [ADR-005](../docs/adr/ADR-005-macro-expert-head.md) | Macro Expert Head | Accepted |
| [ADR-006](../docs/adr/ADR-006-xlf-primary-asset.md) | XLF Primary Asset | Accepted |
| [ADR-007](../docs/adr/ADR-007-yield-slope-removed.md) | Yield Slope Removed | Accepted |
| [ADR-008](../docs/adr/ADR-008-five-year-window.md) | Five-Year Window | Accepted |
| [ADR-009](../docs/adr/ADR-009-trade-count-accepted.md) | Trade Count Accepted | Accepted |
| [ADR-010](../docs/adr/ADR-010-driver-atlas.md) | Driver Atlas | Accepted |
| [ADR-011](ADR-011-january-2027-known-issues.md) | Known Issues — January 2027 Retrain | Resolved |
| [ADR-011a](../docs/adr/ADR-011a-eurusd-unblocked.md) | EURUSD Unblocked | Accepted |
| [ADR-012](../docs/adr/ADR-012-three-asset-portfolio.md) | Three-Asset Portfolio | Accepted |
| [ADR-013](../docs/adr/ADR-013-bootstrap-validation.md) | Bootstrap Validation | Accepted |
| [ADR-014](../docs/adr/ADR-014-zero-overrides-policy.md) | Zero Overrides Policy | Accepted |
| [ADR-015](../docs/adr/ADR-015-asset-specific-label-horizons.md) | Asset-Specific Label Horizons (fwd60) | Accepted |
| [ADR-016](../docs/adr/ADR-016-gold-validation.md) | GC=F Validation with fwd60 | Accepted |
| [ADR-017](../docs/adr/ADR-017-inference-lookahead-investigation.md) | Inference Lookahead Investigation | Accepted |

## Template

Each ADR follows this format:

```markdown
# ADR-{NNN}: {Title}

## Status

[Proposed | Accepted | Deprecated | Superseded]

## Context

## Decision

## Consequences
```
