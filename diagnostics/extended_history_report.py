"""Compare survival bootstrap metrics between default and extended history windows."""

from __future__ import annotations

import argparse
import json
import logging
import os

logger = logging.getLogger("quantforge.extended_history_report")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(PROJECT_ROOT, "data", "research", "extended_history_comparison.json")


def _load_metrics(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def compare_reports(baseline: dict, extended: dict) -> dict:
    """Extract Sharpe, max drawdown, and ruin rate from survival_sim JSON outputs."""
    keys = ("sharpe", "max_drawdown", "ruin_rate", "median_return")
    rows = {}
    for key in keys:
        b = baseline.get(key) or baseline.get("portfolio", {}).get(key)
        e = extended.get(key) or extended.get("portfolio", {}).get(key)
        if b is not None and e is not None:
            rows[key] = {"baseline_5y": b, "extended_25y": e, "delta": e - b if isinstance(b, (int, float)) else None}
    return rows


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Compare 5y vs extended-history survival stats")
    parser.add_argument("--baseline", default=os.path.join(PROJECT_ROOT, "data", "research", "survival_baseline.json"))
    parser.add_argument("--extended", default=os.path.join(PROJECT_ROOT, "data", "research", "survival_extended.json"))
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    baseline = _load_metrics(args.baseline)
    extended = _load_metrics(args.extended)
    if baseline is None or extended is None:
        logger.error(
            "Missing input JSON. Run survival_sim twice (default and --extended-history), "
            "then save outputs to %s and %s",
            args.baseline,
            args.extended,
        )
        return 1

    report = compare_reports(baseline, extended)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Wrote comparison to %s", args.out)
    for metric, vals in report.items():
        logger.info("%s: baseline=%s extended=%s", metric, vals.get("baseline_5y"), vals.get("extended_25y"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
