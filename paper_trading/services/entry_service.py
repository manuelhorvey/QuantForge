import logging

import numpy as np
import pandas as pd
import pytz

from paper_trading.entry.decision import EntryAction, PositionIntent, PositionSide, TradeDecision
from paper_trading.entry.deferred_entry import DeferredEntry, DeferredEntryStatus
from paper_trading.governance.multipliers import compute_effective_multipliers

logger = logging.getLogger("quantforge.entry_service")

ET = pytz.timezone("US/Eastern")


class EntryService:
    def __init__(self, asset):
        self.asset = asset

    def effective_capital(self) -> float:
        asset = self.asset
        if asset.initial_capital <= 0:
            return asset.capital_base
        growth = asset.current_value / asset.initial_capital
        return asset.capital_base * growth

    def tb_vol(self, close_series):
        returns = np.log(close_series / close_series.shift(1))
        vol = returns.ewm(span=100).std()
        return vol.iloc[-1] if not pd.isna(vol.iloc[-1]) else 0.01

    def composite_size_scalar(self, extra_scalar: float = 1.0) -> float:
        asset = self.asset
        _, _, effective_size = compute_effective_multipliers(
            base_sl=asset.sl_mult,
            base_tp=asset.tp_mult,
            validity_state=asset.validity_sm.current_state.value if asset.validity_sm else "YELLOW",
            regime_geometry=asset.regime_geometry,
            narrative_sl_mult=asset.governance._narrative_sl_mult,
            liquidity_sl_mult=asset.governance._liquidity_sl_mult,
            narrative_size_scalar=asset.governance._narrative_size_scalar,
            liquidity_size_scalar=asset.governance._liquidity_size_scalar,
        )
        return (
            asset.pos_mgr.position_size
            * asset.pos_mgr.exposure_multiplier
            * extra_scalar
            * asset._meta_size_multiplier()
            * effective_size
        )

    def compute_notional(self, extra_scalar: float = 1.0) -> float:
        return self.effective_capital() * self.composite_size_scalar(extra_scalar)

    def sizing_config(self, close: pd.Series, position_size_scalar: float = 1.0) -> dict:
        asset = self.asset
        cfg = dict(asset.config)
        if asset.execution_bridge is None:
            return cfg
        price = float(close.iloc[-1]) if len(close) else 0.0
        if price <= 0:
            return cfg
        notional = self.compute_notional(position_size_scalar)
        cfg["impact_bps"] = asset.execution_bridge.estimate_impact_bps(asset.ticker, notional)
        return cfg

    def can_enter(self, side, price, context=None) -> tuple[bool, str]:
        asset = self.asset
        if asset._last_stop_out_date is not None and asset._last_stop_out_side == side:
            now = pd.Timestamp.now(tz="UTC")
            if asset._last_stop_out_date == now.normalize():
                return False, "same_day_stopout_lock"

        penalty = asset._position.cooldown_penalty(side)
        if penalty > 0:
            return False, f"cooldown_active_{penalty:.2f}"

        if side in asset._pending_entries:
            return False, "pending_entry_exists"

        cycles_since_flip = asset._cycle_counter - asset._last_signal_flip_cycle
        if cycles_since_flip < asset._min_flip_interval_bars:
            return False, f"signal_flip_cooldown_{cycles_since_flip}"

        return True, "ok"

    def _validity_state(self) -> str:
        asset = self.asset
        return asset.validity_sm.current_state.value if asset.validity_sm else "YELLOW"

    def _effective_sl_multiplier(self, state: str) -> float:
        asset = self.asset
        curr_sl_mult, _, _ = compute_effective_multipliers(
            base_sl=asset.sl_mult,
            base_tp=asset.tp_mult,
            validity_state=state,
            regime_geometry=asset.regime_geometry,
            narrative_sl_mult=asset.governance._narrative_sl_mult,
            liquidity_sl_mult=asset.governance._liquidity_sl_mult,
            narrative_size_scalar=asset.governance._narrative_size_scalar,
            liquidity_size_scalar=asset.governance._liquidity_size_scalar,
        )
        return curr_sl_mult

    def _take_profit_geometry(self, entry_price: float, close: pd.Series, archetype: str, structure):
        from paper_trading.entry.tp_compiler import compute_take_profit

        state = self._validity_state()
        sl_dist = entry_price * self.tb_vol(close) * self._effective_sl_multiplier(state)
        return compute_take_profit(entry_price, sl_dist, state, archetype, structure)

    @staticmethod
    def _policy_hash(policy_dec) -> str:
        return str(
            hash((
                policy_dec.action,
                policy_dec.archetype,
                policy_dec.reason,
                str(policy_dec.entry_plan),
                str(policy_dec.exit_plan),
            ))
        )[:12]

    def _route_policy(self, entry_action, decision: TradeDecision, structure, tp_geo=None, deferred=None):
        asset = self.asset
        policy_dec = asset._execution_policy.handle(
            entry_action,
            decision,
            decision.archetype,
            structure,
            tp_geo=tp_geo,
            deferred=deferred,
        )
        asset._last_policy_hash = self._policy_hash(policy_dec)
        return policy_dec

    def handle_immediate_entry_policy(self, side: PositionSide, decision: TradeDecision, df: pd.DataFrame) -> None:
        asset = self.asset
        structure = asset._structure_detector.detect(df)
        entry_action = asset._entry_optimizer.evaluate(
            decision.signal,
            decision.archetype,
            structure,
            asset.config.get("entry_optimization", {}),
        )

        tp_geo = None
        deferred_entry = None
        if entry_action == EntryAction.ENTER:
            tp_geo = self._take_profit_geometry(
                float(decision.close_price),
                df["close"],
                decision.archetype,
                structure,
            )
        elif entry_action == EntryAction.DEFER:
            deferred_entry = DeferredEntry.from_decision(
                decision,
                max_bars=asset.config.get("entry_defer_max_bars", 5),
            )

        policy_dec = self._route_policy(entry_action, decision, structure, tp_geo=tp_geo, deferred=deferred_entry)

        if policy_dec.action == EntryAction.ENTER:
            logger.info(f"{asset.name}: POLICY APPROVED ENTER ({policy_dec.reason})")
            self.open_position(side, decision.close_price, decision.timestamp, df, tp_geo=policy_dec.exit_plan)
            if asset.position is not None:
                asset.position["confidence"] = decision.confidence
                asset.position["policy_reason"] = policy_dec.reason

        elif policy_dec.action == EntryAction.DEFER:
            if policy_dec.entry_plan:
                asset._pending_entries[side.value] = policy_dec.entry_plan
                logger.info(f"{asset.name}: POLICY APPROVED DEFER ({policy_dec.reason})")

        else:
            logger.info(f"{asset.name}: POLICY APPROVED SKIP ({policy_dec.reason})")

    def open_position(self, side, entry_price, entry_date, df=None, tp_geo=None):
        asset = self.asset
        data = df if df is not None else asset.price_data
        vol = self.tb_vol(data["close"])
        if pd.isna(vol) or pd.isna(entry_price) or entry_price == 0:
            logger.warning("%s: skipped entry — invalid price=%s or vol=%s", asset.name, entry_price, vol)
            return

        state = asset.validity_sm.current_state.value if asset.validity_sm else "YELLOW"
        sl_mult, tp_mult, _ = compute_effective_multipliers(
            base_sl=asset.sl_mult,
            base_tp=asset.tp_mult,
            validity_state=state,
            regime_geometry=asset.regime_geometry,
            narrative_sl_mult=asset.governance._narrative_sl_mult,
            liquidity_sl_mult=asset.governance._liquidity_sl_mult,
            narrative_size_scalar=asset.governance._narrative_size_scalar,
            liquidity_size_scalar=asset.governance._liquidity_size_scalar,
        )

        fill_price = entry_price
        entry_slippage_bps = 0.0
        if asset.execution_bridge is not None:
            broker_side = "buy" if side == "long" else "sell"
            notional = self.compute_notional()
            qty = max(notional / entry_price, 1e-6)
            fill_price, entry_slippage_bps, _ = asset.execution_bridge.fill_price(
                asset.ticker, broker_side, qty, entry_price
            )
        asset._last_entry_slippage = entry_slippage_bps

        if asset.config.get("dynamic_sltp", {}).get("enabled", False):
            regime = getattr(asset, "_current_regime", "neutral")
            sltp_result = asset._sltp_engine.compute_barriers(
                entry_price=fill_price,
                side=side,
                df=data,
                sl_mult=sl_mult,
                tp_mult=tp_mult,
                regime=regime,
                vol=vol,
                meta_confidence=asset._last_meta_proba,
            )
            intent = PositionIntent(
                side=side,
                entry_price=fill_price,
                entry_date=entry_date,
                stop_loss=sltp_result.stop_loss,
                take_profit=sltp_result.take_profit,
                vol=vol,
            )
        else:
            intent = PositionIntent.from_price_and_vol(side, fill_price, entry_date, vol, sl_mult, tp_mult)

        if tp_geo is None:
            from paper_trading.entry.tp_compiler import compute_take_profit

            sl_dist = abs(intent.stop_loss - fill_price)
            tp_geo = compute_take_profit(
                fill_price,
                sl_dist,
                state,
                getattr(asset, "_entry_archetype", "UNKNOWN"),
                asset._structure_detector.detect(data),
            )

        if side == PositionSide.LONG:
            intent.take_profit = fill_price + tp_geo.tp_distance
        else:
            intent.take_profit = fill_price - tp_geo.tp_distance

        asset.pos_mgr.open(intent)

        if asset._shadow_sltp is not None:
            asset._shadow_sltp.record_entry(
                side=side,
                entry_price=float(fill_price),
                entry_date=entry_date,
                df=data,
                sl_mult=sl_mult,
                tp_mult=tp_mult,
                regime=getattr(asset, "_current_regime", "neutral"),
                meta_confidence=getattr(asset, "_last_meta_proba", None),
            )

        asset.position = {
            "side": intent.side,
            "entry": intent.entry_price,
            "sl": intent.stop_loss,
            "tp": intent.take_profit,
            "entry_date": intent.entry_date,
            "vol": intent.vol,
            "sl_mult": sl_mult,
            "tp_mult": tp_mult,
            "tp_geo": tp_geo,
        }
        asset._entry_vol = vol
        asset._bars_at_entry = 0
        asset._initial_sl = float(intent.stop_loss)
        asset._initial_tp = float(intent.take_profit)

        if asset.config.get("dynamic_sltp", {}).get("enabled", False) and asset._initial_sl is not None:
            asset._sltp_engine.reset_best_price(fill_price)

        asset._entry_price = intent.entry_price
        asset._regime_adjusted_entry = asset.regime_geometry.get(state, {}).get("sl_mult", 1.0) < 1.0

        trade_id = f"{entry_date}_{side}_{asset.name}"
        asset._current_trade_id = trade_id
        entry_action_type = "immediate" if asset._pending_entries.get(side) is None else "deferred"
        deferred_bars = 0
        if entry_action_type == "deferred" and side in asset._pending_entries:
            deferred_bars = (
                asset._pending_entries[side]._bars_pending
                if hasattr(asset._pending_entries.get(side), "_bars_pending")
                else 0
            )

        asset._attribution.record_prediction(
            trade_id=trade_id,
            signal=side,
            label=getattr(asset, "_last_label", 0),
            confidence=getattr(asset, "_last_confidence", 0.0),
            prob_long=getattr(asset, "_last_prob_long", 0.0),
            prob_short=getattr(asset, "_last_prob_short", 0.0),
            prob_neutral=getattr(asset, "_last_prob_neutral", 0.0),
            meta_proba=getattr(asset, "_last_meta_proba", None),
            regime_at_entry=getattr(asset, "_current_regime", "neutral"),
            archetype_at_entry=getattr(asset, "_entry_archetype", "UNKNOWN"),
        )
        asset._attribution.record_execution(
            trade_id=trade_id,
            entry_type=entry_action_type,
            deferred_bars=deferred_bars,
            entry_price=float(fill_price),
            mid_price_at_signal=float(entry_price),
            entry_slippage_bps=entry_slippage_bps,
        )
        asset._attribution.record_friction(
            trade_id=trade_id,
            entry_slippage_bps=entry_slippage_bps,
            exit_slippage_bps=0.0,
        )
        asset._attribution.record_decision_quality(
            trade_id=trade_id,
            entry_pressure_pct=getattr(asset, "_entry_pressure", None),
        )

        asset._scale_out_plan = None
        if asset._scale_out_engine is not None:
            asset._scale_out_plan = asset._scale_out_engine.build_plan(
                side, float(intent.entry_price), float(intent.take_profit), tier_specs=tp_geo.scale_out_tiers
            )

    def poll_pending_entries(self, df: pd.DataFrame) -> None:
        asset = self.asset
        if not asset._pending_entries:
            return

        to_remove = []
        structure = asset._structure_detector.detect(df)
        today = str(pd.Timestamp.now(tz=ET).date())

        for direction, entry in asset._pending_entries.items():
            if not entry.is_active:
                to_remove.append(direction)
                continue

            entry.update()
            if entry.status == DeferredEntryStatus.EXPIRED:
                to_remove.append(direction)
                continue

            entry_action = asset._entry_optimizer.evaluate(
                entry.decision.signal, entry.decision.archetype, structure, asset.config.get("entry_optimization", {})
            )

            tp_geo = None
            if entry_action == EntryAction.ENTER:
                tp_geo = self._take_profit_geometry(
                    float(df["close"].iloc[-1]),
                    df["close"] if isinstance(df, pd.DataFrame) and "close" in df.columns else df,
                    entry.decision.archetype,
                    structure,
                )

            policy_dec = self._route_policy(entry_action, entry.decision, structure, tp_geo=tp_geo, deferred=entry)
            asset._entry_archetype = entry.decision.archetype

            if policy_dec.action == EntryAction.ENTER:
                side = PositionSide(direction)
                ok, reason = asset._entry.can_enter(
                    side,
                    float(df["close"].iloc[-1]),
                    {"regime": getattr(asset, "_current_regime", "neutral")},
                )
                if not ok:
                    logger.info(
                        "%s: entry gate blocking deferred %s entry — %s",
                        asset.name,
                        direction,
                        reason,
                    )
                    entry.cancel(reason=reason)
                    to_remove.append(direction)
                    continue
                logger.info(f"{asset.name}: TRIGGERING deferred {direction} entry (Policy: {policy_dec.reason})")
                entry.trigger(float(df["close"].iloc[-1]))
                self.open_position(side, entry.decision.close_price, today, df, tp_geo=policy_dec.exit_plan)
                if asset.position is not None:
                    asset.position["confidence"] = entry.decision.confidence
                    asset.position["policy_reason"] = policy_dec.reason
                entry.close()
                to_remove.append(direction)

            elif policy_dec.action == EntryAction.SKIP:
                logger.info(f"{asset.name}: CANCELLING deferred {direction} entry (Policy: {policy_dec.reason})")
                entry.cancel(reason=policy_dec.reason)
                to_remove.append(direction)

        for direction in to_remove:
            del asset._pending_entries[direction]
