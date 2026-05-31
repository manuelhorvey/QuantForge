import json
import os
from dataclasses import asdict
from datetime import datetime

import pytz

from paper_trading.api.common import get_vol_baselines, query_window
from paper_trading.config_manager import get_config
from paper_trading.governance.multipliers import compute_governance_multipliers
from paper_trading.ops.market_hours import is_market_closed
from paper_trading.ops.weekly_review import compute_weekly_review
from paper_trading.portfolio_builder import build_paper_portfolio

ET = pytz.timezone("US/Eastern")


class DashboardReadModels:
    def __init__(self, store, confidence_path: str):
        self._store = store
        self._confidence_path = confidence_path

    def state(self) -> dict:
        snapshot = self._store.load_snapshot()
        if snapshot is not None:
            state = asdict(snapshot)
            status = state.setdefault("engine_status", {})
            status["market_closed"] = is_market_closed()
            if "last_update" not in status or status["last_update"] is None:
                status["last_update"] = state.get("timestamp", "")
            self._merge_missing_allocations(state)
            return state

        cfg = get_config()
        pf = build_paper_portfolio(cfg.halt)
        return {
            "engine_status": {
                "initialized": True,
                "last_update": None,
                "start_time": None,
                "market_closed": is_market_closed(),
            },
            "portfolio": {
                "total_value": 0,
                "total_return": 0,
                "days_running": 0,
                "runtime_hours": 0,
                "start_date": "",
                "start_datetime": "",
                "last_update": None,
                "capital": cfg.capital,
                "allocations": {n: spec["alloc"] for n, spec in pf.items()},
                "satellite_allocation_pct": 5.0,
                "deployment_cleared": True,
                "open_positions": 0,
                "closed_trades": 0,
                "execution_state": "ACTIVE",
                "average_validity_exposure": 1.0,
            },
            "assets": {},
            "halt_conditions": dict(cfg.halt),
        }

    @staticmethod
    def _trade_key(trade: dict) -> tuple:
        return (
            trade.get("asset"),
            trade.get("entry_date"),
            trade.get("exit_date"),
            trade.get("reason"),
            round(trade.get("entry", 0), 4),
            round(trade.get("exit", 0), 4),
        )

    @staticmethod
    def _merge_missing_allocations(state: dict) -> None:
        assets = state.get("assets") or {}
        portfolio = state.get("portfolio") or {}
        if not isinstance(portfolio, dict) or not isinstance(assets, dict):
            return
        allocs = portfolio.setdefault("allocations", {})
        cfg = get_config()
        pf = build_paper_portfolio(cfg.halt)
        for name in assets:
            if name not in allocs and name in pf:
                allocs[name] = pf[name]["alloc"]

    def trades(self, query: dict) -> list[dict]:
        limit, offset = query_window(query, default_limit=10, max_limit=200)
        trades = self._store.read_trades(limit + offset)
        seen: set[tuple] = set()
        deduped: list[dict] = []

        for trade in trades:
            key = self._trade_key(trade)
            if key not in seen:
                seen.add(key)
                deduped.append(trade)

        if len(deduped) < limit + offset:
            snapshot = self._store.load_snapshot()
            if snapshot and snapshot.assets:
                for _asset_name, asset_data in snapshot.assets.items():
                    for trade in (asset_data.get("metrics") or {}).get("trade_log") or []:
                        if trade.get("exit_date") is None:
                            continue
                        key = self._trade_key(trade)
                        if key not in seen:
                            seen.add(key)
                            deduped.append(trade)
                deduped.sort(key=lambda x: x.get("exit_date", ""), reverse=True)

        return deduped[offset : offset + limit]

    def equity_history(self) -> list[dict]:
        return self._store.read_equity_history()

    def confidence(self) -> dict:
        snapshot = self._store.load_snapshot()
        if not (snapshot and snapshot.assets):
            return {"live": {}, "historical": []}

        live = {}
        for name, asset in snapshot.assets.items():
            sig = asset.get("last_signal") or {}
            conf = sig.get("confidence", 0)
            bucket_low = min(int(conf // 10) * 10, 90)
            bucket = f"{bucket_low}-{bucket_low + 10}"
            live.setdefault(name, {})
            live[name][bucket] = live[name].get(bucket, 0) + 1

        historical = []
        try:
            if os.path.exists(self._confidence_path):
                import pandas as pd

                df = pd.read_parquet(self._confidence_path)
                historical = json.loads(df.to_json(orient="records", default_handler=str))
        except Exception:
            pass
        return {"live": live, "historical": historical}

    def volatility(self) -> list[dict]:
        snapshot = self._store.load_snapshot()
        regimes = []
        vol_baselines = get_vol_baselines()
        if snapshot and snapshot.assets:
            for name, asset in sorted(snapshot.assets.items()):
                training_vol = vol_baselines.get(name)
                metrics = asset.get("metrics") or {}
                pos = metrics.get("position") or {}
                current_vol = pos.get("current_vol") if pos else None
                if training_vol is not None and current_vol is not None:
                    ratio = current_vol / training_vol
                    if 0.80 <= ratio <= 1.20:
                        status = "green"
                    elif (0.70 <= ratio < 0.80) or (1.20 < ratio <= 1.30):
                        status = "amber"
                    else:
                        status = "red"
                    regimes.append(
                        {
                            "asset": name,
                            "training_vol": training_vol,
                            "current_vol": current_vol,
                            "ratio": round(ratio, 4),
                            "status": status,
                        }
                    )
        return regimes

    def shadow_actions(self) -> dict:
        snapshot = self._store.load_snapshot()
        return getattr(snapshot, "shadow_actions", None) if snapshot else {}

    def shadow_action(self, asset: str):
        return (self.shadow_actions() or {}).get(asset)

    def governance(self) -> dict:
        snapshot = self._store.load_snapshot()
        governance = {}
        if snapshot and snapshot.assets:
            for name, asset in sorted(snapshot.assets.items()):
                validity = (asset.get("validity_state") or "YELLOW").upper()
                regime_sl, combined_sl, regime_size, combined_size, floor_active = compute_governance_multipliers(
                    validity_state=validity,
                    regime_geometry=asset.get("regime_geometry") or {},
                    narrative_sl_mult=asset.get("narrative_sl_mult", 1.0),
                    liquidity_sl_mult=asset.get("liquidity_sl_mult", 1.0),
                    narrative_size_scalar=asset.get("narrative_size_scalar", 1.0),
                    liquidity_size_scalar=asset.get("liquidity_size_scalar", 1.0),
                )
                governance[name] = {
                    "regime_sl_mult": regime_sl,
                    "regime_size_scalar": regime_size,
                    "narrative_sl_mult": asset.get("narrative_sl_mult", 1.0),
                    "narrative_size_scalar": asset.get("narrative_size_scalar", 1.0),
                    "liquidity_sl_mult": asset.get("liquidity_sl_mult", 1.0),
                    "liquidity_size_scalar": asset.get("liquidity_size_scalar", 1.0),
                    "combined_sl_mult": round(combined_sl, 4),
                    "combined_size_scalar": round(combined_size, 4),
                    "floor_active": floor_active,
                    "validity_state": validity,
                    "narrative_regime": asset.get("narrative_regime"),
                    "narrative_stale": asset.get("narrative_stale", False),
                    "liquidity_regime": asset.get("liquidity_regime", "NORMAL"),
                    "halted": asset.get("halt", {}).get("halted", False),
                    "soft_warnings": asset.get("soft_warnings", []),
                }
        return governance

    def risk_parity(self) -> dict:
        snapshot = self._store.load_snapshot()
        return getattr(snapshot, "risk_parity", None) if snapshot else {}

    def liquidity(self) -> dict:
        snapshot = self._store.load_snapshot()
        regimes = {}
        if snapshot and snapshot.assets:
            for name, asset in sorted(snapshot.assets.items()):
                regimes[name] = {
                    "regime": asset.get("liquidity_regime", "NORMAL"),
                    "sl_mult": asset.get("liquidity_sl_mult", 1.0),
                    "size_scalar": asset.get("liquidity_size_scalar", 1.0),
                }
        return regimes

    def psi(self) -> dict:
        snapshot = self._store.load_snapshot()
        psi_data = {}
        if snapshot and snapshot.assets:
            for name, asset in sorted(snapshot.assets.items()):
                metrics = asset.get("metrics", {})
                psi = metrics.get("psi_drift", {})
                if psi and psi.get("per_feature"):
                    psi_data[name] = {
                        "per_feature": psi["per_feature"],
                        "worst_classification": psi.get("worst_classification", "NO_DRIFT"),
                        "moderate_count": psi.get("moderate_count", 0),
                        "severe_count": psi.get("severe_count", 0),
                        "psi_ok": psi.get("psi_ok", True),
                        "penalty": psi.get("penalty", 0.0),
                    }
        return psi_data

    def trade_outcomes(self) -> dict:
        return self._store.read_trade_outcomes() or {"overall": {}, "by_asset": [], "updated_at": ""}

    def weekly_review(self) -> dict:
        return compute_weekly_review(self._store)

    def attribution_trades(self, query: dict) -> list[dict]:
        limit, offset = query_window(query, default_limit=50, max_limit=500)
        return self._store.read_attribution(
            limit=limit,
            offset=offset,
            archetype=query.get("archetype") or None,
            regime=query.get("regime") or None,
            asset=query.get("asset") or None,
        )

    def _attribution_records(self, query: dict, *, default_limit: int = 500, max_limit: int = 2000) -> list[dict]:
        limit, _offset = query_window(query, default_limit=default_limit, max_limit=max_limit)
        return self._store.read_attribution(limit=limit)

    def attribution_summary(self, query: dict) -> dict:
        records = self._attribution_records(query)
        if not records:
            return {"by_archetype": {}, "by_regime": {}, "overall": {}}

        from shared.metrics.attribution import compute_aggregate_domain_scores
        from shared.metrics.mae_mfe import compute_mae_mfe_stats

        domain_scores = compute_aggregate_domain_scores(records)
        mae_mfe = compute_mae_mfe_stats(records)
        return {
            "overall": {
                "n_trades": mae_mfe["overall"]["n"],
                "avg_r": mae_mfe["overall"]["avg_mfe_mae_ratio"],
                "avg_mae_pct": mae_mfe["overall"]["avg_mae_pct"],
                "avg_mfe_pct": mae_mfe["overall"]["avg_mfe_pct"],
                "domain_scores": domain_scores["overall"],
            },
            "by_archetype": mae_mfe.get("by_archetype", {}),
            "by_regime": mae_mfe.get("by_regime", {}),
            "domain_scores": domain_scores.get("by_archetype", {}),
            "updated_at": datetime.now(tz=ET).isoformat(),
        }

    def execution_quality(self, query: dict) -> dict:
        records = self._attribution_records(query)
        if not records:
            return {"by_asset": {}}

        import pandas as pd

        from shared.metrics.eis import compute_eis_from_df
        from shared.metrics.fqi import compute_fqi_from_df

        df = pd.DataFrame(records)
        eis_by_asset = compute_eis_from_df(df)
        fqi_by_asset = compute_fqi_from_df(df)
        has_entry_slip = "friction_entry_slippage_bps" in df.columns
        has_exit_slip = "friction_exit_slippage_bps" in df.columns
        has_latency = "friction_latency_bars" in df.columns
        has_gap = "friction_gap_fill" in df.columns
        has_partial = "friction_partial_fill" in df.columns
        has_fill_ratio = "friction_fill_qty_ratio" in df.columns

        by_asset = {}
        for asset_name, grp in df.groupby("asset"):
            by_asset[asset_name] = {
                "n": len(grp),
                "eis": eis_by_asset.get(asset_name),
                "fqi": fqi_by_asset.get(asset_name),
                "avg_entry_slippage_bps": round(float(grp["friction_entry_slippage_bps"].mean()), 2)
                if has_entry_slip
                else 0.0,
                "avg_exit_slippage_bps": round(float(grp["friction_exit_slippage_bps"].mean()), 2)
                if has_exit_slip
                else 0.0,
                "avg_latency_bars": round(float(grp["friction_latency_bars"].mean()), 2) if has_latency else 0.0,
                "gap_rate": round(float(grp["friction_gap_fill"].mean()), 4) if has_gap else 0.0,
                "partial_fill_rate": round(float(grp["friction_partial_fill"].mean()), 4) if has_partial else 0.0,
                "avg_fill_ratio": round(float(grp["friction_fill_qty_ratio"].mean()), 4) if has_fill_ratio else 1.0,
            }
        return {"by_asset": by_asset}

    def execution_slippage(self, query: dict) -> dict:
        records = self._attribution_records(query)
        if not records:
            return {"entry_slippage": [], "exit_slippage": []}

        entry_slippage = []
        exit_slippage = []
        gap_count = 0
        partial_count = 0
        for record in records:
            es = record.get("friction_entry_slippage_bps")
            xs = record.get("friction_exit_slippage_bps")
            if es is not None:
                entry_slippage.append(float(es))
            if xs is not None:
                exit_slippage.append(float(xs))
            if record.get("friction_gap_fill"):
                gap_count += 1
            if record.get("friction_partial_fill"):
                partial_count += 1
        return {
            "entry_slippage": entry_slippage,
            "exit_slippage": exit_slippage,
            "gap_count": gap_count,
            "partial_fill_count": partial_count,
            "n": len(records),
        }

    def shadow_trades(self, query: dict) -> list[dict]:
        limit, offset = query_window(query, default_limit=50, max_limit=500)
        return self._store.read_shadow_trades(
            limit=limit,
            offset=offset,
            alt_label=query.get("alt_label") or None,
        )

    def shadow_summary(self, query: dict) -> dict:
        limit, _offset = query_window(query, default_limit=500, max_limit=2000)
        records = self._store.read_shadow_trades(limit=limit)
        if not records:
            return {"overall": {"n": 0}}

        from shared.metrics.shadow import compute_shadow_divergence

        result = compute_shadow_divergence(records)
        result["updated_at"] = datetime.now(tz=ET).isoformat()
        return result

    def analytics_snapshot(self) -> dict:
        return self._store.read_analytics_snapshot() or {
            "overall": {},
            "by_archetype": {},
            "by_regime": {},
            "shadow": {},
        }

    def attribution_waterfall(self, query: dict) -> dict:
        records = self._attribution_records(query)
        if not records:
            return {
                "prediction_pnl": 0.0,
                "execution_cost": 0.0,
                "exit_cost": 0.0,
                "friction_cost": 0.0,
                "net_pnl": 0.0,
                "n": 0,
            }

        from shared.metrics.attribution import compute_waterfall

        result = compute_waterfall(records)
        result["updated_at"] = datetime.now(tz=ET).isoformat()
        return result

    def archetype_stats(self, query: dict) -> dict:
        records = self._attribution_records(query)
        if not records:
            return {"by_archetype": {}}

        import pandas as pd

        df = pd.DataFrame(records)
        arch_col = "pred_archetype_at_entry"
        by_archetype = {}
        if arch_col in df.columns:
            for arch, grp in df.groupby(arch_col):
                by_archetype[arch] = {
                    "n": len(grp),
                    "avg_r": float(grp.get("exit_realized_r", 0).mean()),
                    "win_rate": float((grp.get("exit_realized_r", 0) > 0).mean()),
                    "tp_rate": float((grp.get("exit_exit_reason", "") == "tp").mean()),
                    "sl_rate": float((grp.get("exit_exit_reason", "") == "sl").mean()),
                    "avg_mae": float(grp.get("exit_mae", 0).mean()),
                    "avg_mfe": float(grp.get("exit_mfe", 0).mean()),
                    "avg_entry_slippage_bps": float(grp.get("friction_entry_slippage_bps", 0).mean()),
                    "avg_bars_held": float(grp.get("exit_bars_held", 0).mean()),
                }
        return {"by_archetype": by_archetype}
