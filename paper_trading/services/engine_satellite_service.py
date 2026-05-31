import logging
from datetime import datetime

import pandas as pd
import pytz

from paper_trading.config_manager import get_config
from paper_trading.satellite.engine import HighVolSatellite, SatelliteConfig

logger = logging.getLogger("quantforge.engine_satellite_service")

ET = pytz.timezone("US/Eastern")


class EngineSatelliteService:
    def __init__(self, engine):
        self.engine = engine

    def init_satellite(self) -> None:
        engine = self.engine
        engine.satellite = None
        sat_cfg = get_config().satellite
        btc_sat = sat_cfg.get("BTC", {})
        if btc_sat:
            sconfig = SatelliteConfig(
                max_allocation_pct=btc_sat.get("max_allocation_pct", 0.05),
                vol_target=btc_sat.get("vol_target", 0.40),
                max_drawdown_pct=btc_sat.get("max_drawdown_pct", -0.25),
                sl_mult=btc_sat.get("sl_mult", 0.58),
                tp_mult=btc_sat.get("tp_mult", 1.51),
            )
            engine.satellite = HighVolSatellite(
                total_aum=get_config().capital,
                config=sconfig,
                name="BTC",
            )

    def run_satellite(self, results: dict) -> None:
        engine = self.engine
        sat = engine.satellite
        if sat is None:
            return

        try:
            import paper_trading.engine as _eng

            btc_price_data = _eng.fetch_btc_price(engine.assets)
            if btc_price_data is None or btc_price_data.empty:
                results["satellite"] = {"asset": "BTC", "error": "no BTC price data"}
                return

            ctx = _eng.compute_btc_context(btc_price_data)
            vix, dxy_mom = _eng.fetch_macro_context()
            core_rets_63d = _eng.compute_core_returns(engine.assets)

            decision = sat.evaluate_gate(
                vix=vix,
                dxy_mom_21=dxy_mom,
                btc_vol_zscore=ctx["vol_zscore"],
                portfolio_returns_63d=core_rets_63d,
                btc_returns_63d=ctx["returns_63d"],
                crisis_regime_active=engine._rebalance.detect_crisis_regime(),
            )

            current_price = float(btc_price_data["close"].ffill().iloc[-1])
            sat.current_price = current_price
            returns_all = ctx.get("returns_all")
            current_return = float(returns_all[-1]) if returns_all is not None and len(returns_all) >= 1 else 0.0

            if returns_all is not None and len(returns_all) >= 20:
                returns_series = pd.Series(returns_all)
                vol = float(returns_series.ewm(span=100).std().iloc[-1])
            else:
                vol = 0.45

            if sat.initial_capital == 0.0:
                sat.deploy_capital(sat.max_capital)
                logger.info("BTC satellite: deployed capital %.2f", sat.max_capital)

            sat_entry = sat.entry_price
            sat_entry_date = getattr(sat, "position_entry_date", None)
            sat_entry_capital = getattr(sat, "_entry_capital", 0.0)
            sat_stop = sat.stop_price
            was_active = sat.position_active

            sat.record_return(current_return)
            if sat.position_active and sat.entry_price is not None and sat.entry_price > 0:
                entry_capital = sat._entry_capital or sat.max_capital or sat.current_value
                sat.current_value = entry_capital * (current_price / sat.entry_price)
                sat.peak_value = max(sat.peak_value, sat.current_value)

            exit_reason = sat.check_exit(current_price) if sat.position_active else None

            if exit_reason is None:
                if decision.allowed and not sat.position_active:
                    sat.open_position(entry_price=current_price, vol=vol)
                elif not decision.allowed and sat.position_active:
                    sat.close_position(reason="GATE_CLOSED")

            if was_active and not sat.position_active and sat._last_exit_reason is not None:
                exit_price = current_price
                pnl_pct = (exit_price / sat_entry - 1.0) if sat_entry else 0.0
                risk_pct = abs(sat_entry - sat_stop) / sat_entry if sat_stop and sat_entry else 0.0
                r_mult = pnl_pct / risk_pct if risk_pct > 0 else 0.0
                entry_dt = str(sat_entry_date) if sat_entry_date else str(datetime.now(tz=ET).date())
                exit_dt = str(datetime.now(tz=ET).date())
                trade = {
                    "asset": sat.name,
                    "side": "long",
                    "entry": round(float(sat_entry), 4) if sat_entry else None,
                    "exit": round(float(exit_price), 4),
                    "entry_date": entry_dt,
                    "exit_date": exit_dt,
                    "return": round(pnl_pct, 6),
                    "pnl": round(pnl_pct * sat_entry_capital, 2),
                    "total_pnl": round(pnl_pct * sat_entry_capital, 2),
                    "reason": sat._last_exit_reason.lower(),
                    "realized_r": round(r_mult, 4),
                    "bars": 0,
                }
                engine.state_store.append_trade(trade)
                engine.state_store.write_analytics_snapshot()
                sat.trade_log.append(trade)

            logger.info(
                "%s satellite: gate=%s, position=%s, value=%.2f%s",
                sat.name,
                "OPEN" if decision.allowed else "CLOSED",
                "ACTIVE" if sat.position_active else "FLAT",
                sat.current_value,
                f", exit={exit_reason}" if exit_reason else "",
            )

            results["satellite"] = {
                "asset": "BTC",
                "gate_allowed": decision.allowed,
                "gate_reasons": decision.reasons_blocked,
                "position_active": sat.position_active,
                "current_value": round(sat.current_value, 2),
                "current_price": round(current_price, 2),
                "entry_price": sat.entry_price,
                "stop_price": sat.stop_price,
                "target_price": sat.target_price,
                "exit_reason": sat._last_exit_reason,
            }
        except Exception as e:
            logger.error("satellite gating failed: %s", e)
            results["satellite"] = {"asset": "BTC", "error": str(e)}

    def run_satellite_only(self) -> dict:
        engine = self.engine
        results: dict[str, object] = {}
        if engine.satellite is not None:
            try:
                self.run_satellite(results)
            except Exception as e:
                logger.error("satellite weekend run failed: %s", e)
                results["satellite"] = {"asset": "BTC", "error": str(e)}
        if not results.get("satellite"):
            results["satellite"] = {"asset": "BTC", "message": "no satellite configured"}
        return results
