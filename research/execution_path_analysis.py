"""Execution path diagnostics — archetype-conditioned MAE/MFE analysis.

This module is the research counterpart of the frozen execution
infrastructure.  It reads attribution data produced by the live
engine and shadow engines, then produces distributional statistics
to answer execution-research questions:

  - What fraction of BREAKOUT trades reaching +0.7R later revert to SL?
  - What is the conditional MFE distribution after deferred entries?
  - How does entry_slippage_bps correlate with MAE expansion?
  - Does archetype drift predict premature stop-outs?
  - What trailing-stage thresholds are supported by the data?

Usage::

    python -m research.execution_path_analysis --attribution-dir data/research/attribution

Architecture: pure analysis — never mutates live state, never writes
to live artifacts.  Outputs go to ``data/research/execution_path/``.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger("quantforge.execution_path_analysis")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "research", "execution_path")


@dataclass
class ArchetypePathStats:
    """Distributional statistics for one archetype."""
    n_trades: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    sl_rate: float = 0.0
    tp_rate: float = 0.0
    trailing_rate: float = 0.0
    signal_flip_rate: float = 0.0
    avg_mae: float = 0.0
    avg_mfe: float = 0.0
    avg_bars_held: float = 0.0
    mfe_distribution: list[float] = field(default_factory=list)
    mae_distribution: list[float] = field(default_factory=list)
    reversal_after_05r: float = 0.0   # fraction that reached +0.5R then hit SL
    reversal_after_10r: float = 0.0   # fraction that reached +1.0R then hit SL
    reversal_after_15r: float = 0.0   # fraction that reached +1.5R then hit SL


@dataclass
class MetaBucketStats:
    """Outcome statistics stratified by meta-confidence decile."""
    bucket: str = ""
    n_trades: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    avg_mfe: float = 0.0
    avg_mae: float = 0.0
    tp_rate: float = 0.0
    sl_rate: float = 0.0


def load_attribution(attribution_dir: str) -> pd.DataFrame:
    """Load all attribution parquet files into a single DataFrame."""
    all_frames = []
    for fname in os.listdir(attribution_dir):
        if not fname.endswith("_attribution.parquet"):
            continue
        path = os.path.join(attribution_dir, fname)
        df = pd.read_parquet(path)
        all_frames.append(df)
    if not all_frames:
        logger.warning("no attribution data found in %s", attribution_dir)
        return pd.DataFrame()
    combined = pd.concat(all_frames, ignore_index=True)
    logger.info("loaded %d attribution records from %d files", len(combined), len(all_frames))
    return combined


def compute_archetype_stats(df: pd.DataFrame) -> dict[str, ArchetypePathStats]:
    """Compute per-archetype path statistics from attribution data."""
    # Expect columns: pred_archetype_at_entry, exit_exit_reason, exit_realized_r,
    # exit_mae, exit_mfe, exit_bars_held
    if df.empty:
        return {}

    archetype_col = "pred_archetype_at_entry"
    if archetype_col not in df.columns:
        logger.warning("column %s not found — checking alternatives", archetype_col)
        archetype_col = next((c for c in df.columns if "archetype" in c.lower()), None)
        if archetype_col is None:
            logger.error("no archetype column found in attribution data")
            return {}

    stats: dict[str, ArchetypePathStats] = {}
    for archetype, group in df.groupby(archetype_col):
        n = len(group)
        s = ArchetypePathStats(n_trades=n)

        # Exit reason rates
        reasons = group.get("exit_exit_reason", pd.Series())
        s.sl_rate = float((reasons == "sl").mean()) if n > 0 else 0.0
        s.tp_rate = float((reasons == "tp").mean()) if n > 0 else 0.0
        s.trailing_rate = float((reasons == "trailing").mean()) if n > 0 else 0.0
        s.signal_flip_rate = float((reasons == "signal_flip").mean()) if n > 0 else 0.0

        # R-multiple
        r_col = "exit_realized_r"
        if r_col in df.columns:
            realized_r = group[r_col].dropna()
            s.avg_r = float(realized_r.mean()) if len(realized_r) > 0 else 0.0
            s.win_rate = float((realized_r > 0).mean()) if len(realized_r) > 0 else 0.0

        # MAE / MFE
        for col, attr in [("exit_mae", "avg_mae"), ("exit_mfe", "avg_mfe")]:
            if col in df.columns:
                vals = group[col].dropna()
                setattr(s, attr, float(vals.mean()) if len(vals) > 0 else 0.0)
                if attr == "avg_mfe":
                    s.mfe_distribution = sorted(vals.tolist()) if len(vals) > 0 else []
                elif attr == "avg_mae":
                    s.mae_distribution = sorted(vals.tolist()) if len(vals) > 0 else []

        # Bars held
        bars_col = "exit_bars_held"
        if bars_col in df.columns:
            bars = group[bars_col].dropna()
            s.avg_bars_held = float(bars.mean()) if len(bars) > 0 else 0.0

        # Reversal rates: fraction that reached N-R profit then hit SL
        # Requires both MFE and exit_reason — approximate from attribution data
        if "exit_mfe" in df.columns:
            mfe_vals = group["exit_mfe"].dropna()
            # Approximate R-multiple from MFE (requires entry price, approximate via 1% risk)
            # This is a heuristic — true reversal rates need tick-level data
            above_half = (reasons == "sl") & (group.get("exit_mfe", pd.Series(0)) > group.get("exit_realized_r", pd.Series(0)).abs().mean() * 0.5)
            s.reversal_after_05r = float(above_half.mean()) if n > 0 else 0.0

        stats[archetype] = s
        logger.debug("%s: n=%d, win=%.2f, avg_r=%.2f, sl=%.2f, tp=%.2f",
                     archetype, n, s.win_rate, s.avg_r, s.sl_rate, s.tp_rate)

    return stats


def compute_meta_bucket_stats(df: pd.DataFrame) -> list[MetaBucketStats]:
    """Stratify outcomes by meta-confidence decile."""
    meta_col = "exit_meta_bucket"
    if meta_col not in df.columns:
        logger.warning("column %s not found — cannot compute meta-bucket stats", meta_col)
        return []

    buckets = []
    for bucket_name, group in df.groupby(meta_col):
        n = len(group)
        s = MetaBucketStats(bucket=bucket_name, n_trades=n)

        r_col = "exit_realized_r"
        if r_col in df.columns:
            realized_r = group[r_col].dropna()
            s.avg_r = float(realized_r.mean()) if len(realized_r) > 0 else 0.0
            s.win_rate = float((realized_r > 0).mean()) if len(realized_r) > 0 else 0.0

        for col, attr in [("exit_mae", "avg_mae"), ("exit_mfe", "avg_mfe")]:
            if col in df.columns:
                vals = group[col].dropna()
                setattr(s, attr, float(vals.mean()) if len(vals) > 0 else 0.0)

        reasons = group.get("exit_exit_reason", pd.Series())
        s.tp_rate = float((reasons == "tp").mean()) if n > 0 else 0.0
        s.sl_rate = float((reasons == "sl").mean()) if n > 0 else 0.0

        buckets.append(s)

    return sorted(buckets, key=lambda x: x.bucket)


def generate_report(
    df: pd.DataFrame,
    archetype_stats: dict[str, ArchetypePathStats],
    meta_buckets: list[MetaBucketStats],
) -> str:
    """Generate a human-readable execution path analysis report."""
    lines = []
    lines.append("=" * 72)
    lines.append("  EXECUTION PATH DIAGNOSTICS REPORT")
    lines.append("=" * 72)
    lines.append(f"  Total trades analyzed: {len(df)}")
    lines.append(f"  Attribution columns: {list(df.columns)}")
    lines.append("")

    # Archetype breakdown
    lines.append("-" * 72)
    lines.append("  PER-ARCHETYPE EXECUTION STATISTICS")
    lines.append("-" * 72)
    header = f"  {'Archetype':<20} {'N':>6} {'Win%':>7} {'Avg R':>7} {'SL%':>7} {'TP%':>7} {'Trail%':>7} {'MFE':>8} {'MAE':>8} {'Bars':>6}"
    lines.append(header)
    lines.append("  " + "-" * 84)
    for arch, s in sorted(archetype_stats.items()):
        lines.append(
            f"  {arch:<20} {s.n_trades:>6} {s.win_rate:>6.1%} {s.avg_r:>7.2f} "
            f"{s.sl_rate:>6.1%} {s.tp_rate:>6.1%} {s.trailing_rate:>6.1%} "
            f"{s.avg_mfe:>8.4f} {s.avg_mae:>8.4f} {s.avg_bars_held:>6.1f}"
        )
    lines.append("")

    # Meta-bucket stratification
    if meta_buckets:
        lines.append("-" * 72)
        lines.append("  META-CONFIDENCE STRATIFICATION")
        lines.append("-" * 72)
        meta_header = f"  {'Bucket':<14} {'N':>6} {'Win%':>7} {'Avg R':>7} {'TP%':>7} {'SL%':>7} {'MFE':>8} {'MAE':>8}"
        lines.append(meta_header)
        lines.append("  " + "-" * 66)
        for s in meta_buckets:
            lines.append(
                f"  {s.bucket:<14} {s.n_trades:>6} {s.win_rate:>6.1%} {s.avg_r:>7.2f} "
                f"{s.tp_rate:>6.1%} {s.sl_rate:>6.1%} {s.avg_mfe:>8.4f} {s.avg_mae:>8.4f}"
            )
        lines.append("")

    # Reversal risk
    lines.append("-" * 72)
    lines.append("  REVERSAL RISK (trades reaching X profit that hit SL)")
    lines.append("-" * 72)
    lines.append("  (requires tick-level MFE data — approximate from attribution)")
    lines.append("")

    return "\n".join(lines)


def run(attribution_dir: str, output_dir: str | None = None) -> None:
    """Run full execution path analysis."""
    if output_dir is None:
        output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    df = load_attribution(attribution_dir)
    if df.empty:
        logger.warning("no data to analyze")
        return

    archetype_stats = compute_archetype_stats(df)
    meta_buckets = compute_meta_bucket_stats(df)

    report = generate_report(df, archetype_stats, meta_buckets)
    print(report)

    # Save report
    report_path = os.path.join(output_dir, "execution_path_report.txt")
    with open(report_path, "w") as f:
        f.write(report)
    logger.info("report saved to %s", report_path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Execution path diagnostics")
    parser.add_argument("--attribution-dir", default="data/research/attribution",
                        help="Directory containing attribution parquet files")
    parser.add_argument("--output-dir", default=OUTPUT_DIR,
                        help="Output directory for report")
    args = parser.parse_args()
    run(args.attribution_dir, args.output_dir)


if __name__ == "__main__":
    main()
