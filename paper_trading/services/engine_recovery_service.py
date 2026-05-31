import logging

import pytz

from paper_trading.entry.decision import PositionIntent, PositionSide

logger = logging.getLogger("quantforge.engine_recovery_service")

ET = pytz.timezone("US/Eastern")


class EngineRecoveryService:
    def __init__(self, engine):
        self.engine = engine

    def _restore_saved_position(self, asset, pos_data: dict) -> None:
        pos_dict = pos_data.get("position")
        if pos_dict:
            intent = PositionIntent(
                side=PositionSide(pos_dict["side"]),
                entry_price=pos_dict["entry"],
                entry_date=pos_dict["entry_date"],
                stop_loss=pos_dict["sl"],
                take_profit=pos_dict["tp"],
                vol=pos_dict["vol"],
            )
            asset.position = pos_dict
            asset.pos_mgr.open(intent)
        cv = pos_data.get("current_value")
        if cv is not None:
            asset.current_value = cv
            asset.pos_mgr.current_value = cv
        pv = pos_data.get("peak_value")
        if pv is not None:
            asset.peak_value = pv
            asset.pos_mgr.peak_value = pv
        asset.trade_log = pos_data.get("trade_log", [])
        asset.pos_mgr.trade_log = list(pos_data.get("trade_log", []))
        asset.prob_history = pos_data.get("prob_history", [])

    def restore_positions(self, saved_positions: dict) -> None:
        engine = self.engine
        for name, pos_data in saved_positions.items():
            if name in engine.assets:
                self._restore_saved_position(engine.assets[name], pos_data)
            elif name == "satellite" and engine.satellite is not None:
                self._restore_satellite_position(engine.satellite, pos_data)

    def _restore_satellite_position(self, sat, pos_data: dict) -> None:
        pos_dict = pos_data.get("position")
        if pos_dict:
            sat.position_active = True
            sat.position_side = pos_dict["side"]
            sat.entry_price = pos_dict["entry"]
            sat.stop_price = pos_dict["sl"]
            sat.target_price = pos_dict["tp"]
            sat.position_entry_date = pos_dict["entry_date"]
            sat.position_vol = pos_dict["vol"]

        cv = pos_data.get("current_value")
        if cv is not None:
            sat.current_value = cv
        pv = pos_data.get("peak_value")
        if pv is not None:
            sat.peak_value = pv
        ic = pos_data.get("initial_capital")
        if ic is not None:
            sat.initial_capital = ic
        ec = pos_data.get("entry_capital")
        if ec is not None:
            sat._entry_capital = ec
        dr = pos_data.get("daily_returns")
        if dr is not None:
            sat._daily_returns = list(dr)
