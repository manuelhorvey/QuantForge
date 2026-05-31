#!/usr/bin/env python3
"""Generate BASELINE_SNAPSHOT.md from configs/paper_trading.yaml + LIVE_CONTRACT.md.

Usage:
    python scripts/generate_snapshot.py

Output:
    BASELINE_SNAPSHOT.md at project root.
"""

import datetime
import pathlib
import re
import sys

import yaml


def _extract_threshold(contract_text: str) -> str:
    m = re.search(r"Threshold.*?`([\d.]+)`", contract_text)
    return m.group(1) if m else "unknown"


def _extract_contract_section(contract_text: str, section_title: str) -> str:
    lines = contract_text.splitlines()
    capture = False
    section_lines = []
    for line in lines:
        if line.strip().startswith("## ") and section_title in line:
            capture = True
            continue
        if capture:
            if line.strip().startswith("## "):
                break
            section_lines.append(line)
    return "\n".join(section_lines).strip()


def main() -> None:
    base_dir = pathlib.Path(__file__).resolve().parent.parent

    config_path = base_dir / "configs" / "paper_trading.yaml"
    contract_path = base_dir / "LIVE_CONTRACT.md"
    out_path = base_dir / "BASELINE_SNAPSHOT.md"

    if not config_path.exists():
        print(f"ERROR: {config_path} not found", file=sys.stderr)
        sys.exit(1)
    if not contract_path.exists():
        print(f"ERROR: {contract_path} not found", file=sys.stderr)
        sys.exit(1)

    config = yaml.safe_load(config_path.read_text())
    contract = contract_path.read_text()

    threshold = _extract_threshold(contract)
    portfolio_section = _extract_contract_section(contract, "PORTFOLIO CONTRACT")

    lines = [
        "# BASELINE SNAPSHOT",
        "",
        f"Generated: {datetime.date.today()}",
        "Source: configs/paper_trading.yaml + LIVE_CONTRACT.md",
        "DO NOT EDIT — regenerate with `make snapshot`",
        "",
        "---",
        "",
        "## Capital",
        "",
        f"- Starting capital: {config.get('capital', 'unknown')}",
        f"- Position size fraction: {config.get('position_size', 'unknown')}",
        "",
        "## Signal threshold",
        "",
        f"- Threshold: {threshold}",
        "",
        "## Portfolio allocation",
        "",
    ]

    assets = config.get("assets", {})
    for name, cfg in assets.items():
        alloc = cfg.get("allocation", "?")
        sl = cfg.get("sl_mult", "?")
        tp = cfg.get("tp_mult", "?")
        ticker = cfg.get("ticker", "?")
        lines.append(f"- **{name}** ({ticker}): alloc={alloc}, sl_mult={sl}, tp_mult={tp}")

    halt = config.get("execution", {}).get("governance", {})
    lines.extend([
        "",
        "## Halt & governance",
        "",
        f"- Portfolio drawdown limit: {config.get('portfolio_drawdown_limit', '?')}",
        "",
        "## Contract reference",
        "",
        "See LIVE_CONTRACT.md for the full execution contract (model architecture,",
        "feature definitions, label pipeline, inference pipeline, and invariants).",
        "",
    ])

    out_path.write_text("\n".join(lines) + "\n")
    print(f"BASELINE_SNAPSHOT.md written ({len(assets)} assets)")


if __name__ == "__main__":
    main()
