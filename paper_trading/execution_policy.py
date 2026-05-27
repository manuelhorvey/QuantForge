import logging
from typing import Optional, Union
from paper_trading.decision import (
    EntryAction, 
    PolicyDecision, 
    MarketStructureState, 
    TradeDecision, 
    PositionIntent, 
    TPGeometry
)
from paper_trading.deferred_entry import DeferredEntry

logger = logging.getLogger("quantforge.paper_trading.execution_policy")

class BasePolicy:
    """Base class for archetype-specific routing policies."""
    
    @staticmethod
    def route(
        action: EntryAction,
        decision: TradeDecision,
        archetype: str,
        structure: MarketStructureState,
        tp_geo: Optional[TPGeometry],
        deferred: Optional[DeferredEntry]
    ) -> PolicyDecision:
        # Default implementation: strictly follow the pre-decided action
        return PolicyDecision(
            action=action,
            entry_plan=deferred if action == EntryAction.DEFER else None,
            exit_plan=tp_geo if action == EntryAction.ENTER else None,
            reason=f"Standard routing for {archetype}: {action}",
            archetype=archetype,
            metadata={"source": "BasePolicy"}
        )

class MomentumPolicy(BasePolicy):
    """Routing for Momentum Ignition."""
    @staticmethod
    def route(action, decision, archetype, structure, tp_geo, deferred):
        reason = f"Momentum routing: {action}"
        if action == EntryAction.DEFER:
            reason = f"Momentum ignition deferred (Structural Pressure: {structure.breakout_pressure})"
        
        return PolicyDecision(
            action=action,
            entry_plan=deferred if action == EntryAction.DEFER else None,
            exit_plan=tp_geo if action == EntryAction.ENTER else None,
            reason=reason,
            archetype=archetype,
            metadata={"source": "MomentumPolicy", "convexity": tp_geo.convexity_score if tp_geo else None}
        )

class MeanReversionPolicy(BasePolicy):
    """Routing for Mean Reversion."""
    @staticmethod
    def route(action, decision, archetype, structure, tp_geo, deferred):
        return PolicyDecision(
            action=action,
            entry_plan=deferred if action == EntryAction.DEFER else None,
            exit_plan=tp_geo if action == EntryAction.ENTER else None,
            reason=f"Mean reversion routing: {action}",
            archetype=archetype,
            metadata={"source": "MeanReversionPolicy"}
        )

class BreakoutPolicy(BasePolicy):
    """Routing for Breakouts."""
    @staticmethod
    def route(action, decision, archetype, structure, tp_geo, deferred):
        return PolicyDecision(
            action=action,
            entry_plan=deferred if action == EntryAction.DEFER else None,
            exit_plan=tp_geo if action == EntryAction.ENTER else None,
            reason=f"Breakout routing: {action}",
            archetype=archetype,
            metadata={"source": "BreakoutPolicy"}
        )

class ExecutionPolicyLayer:
    """
    Phase 4: Execution Policy Layer Switchboard.
    A deterministic routing compiler over already-frozen decisions.
    Boringly deterministic traffic controller.
    """

    POLICY_MAP = {
        "MOMENTUM_IGNITION": MomentumPolicy,
        "MEAN_REVERSION": MeanReversionPolicy,
        "BREAKOUT_TEST": BreakoutPolicy,
        "TREND_PULLBACK": BasePolicy,
        "VOL_EXPANSION": BasePolicy,
        "UNKNOWN": BasePolicy
    }

    def handle(
        self,
        action: EntryAction,
        decision: TradeDecision,
        archetype: str,
        structure: MarketStructureState,
        tp_geo: Optional[TPGeometry] = None,
        deferred: Optional[DeferredEntry] = None
    ) -> PolicyDecision:
        """
        Routes artifacts into the final immutable execution plan.
        """
        # 1. Resolve Policy
        policy_cls = self.POLICY_MAP.get(archetype.upper(), BasePolicy)
        
        # 2. Compile Decision
        try:
            return policy_cls.route(action, decision, archetype, structure, tp_geo, deferred)
        except Exception as e:
            logger.error(f"Policy routing failed for {archetype}: {e}")
            # Emergency Fallback: strictly follow action with no frills
            return PolicyDecision(
                action=action,
                entry_plan=deferred if action == EntryAction.DEFER else None,
                exit_plan=tp_geo if action == EntryAction.ENTER else None,
                reason=f"Emergency fallback routing for {archetype}",
                archetype=archetype,
                metadata={"emergency": True}
            )

if __name__ == "__main__":
    # Test routing
    layer = ExecutionPolicyLayer()
    from paper_trading.decision import SignalType
    
    dec = TradeDecision("TEST", SignalType.BUY, 2, 75.0, 0.75, 0.1, 0.15, 100.0, "2026-05-26", 1.0, "MOMENTUM_IGNITION")
    struct = MarketStructureState(0, 0, 0, 0, 1.0, 0.95)
    
    # Simulate DEFER from Phase 1
    policy_dec = layer.handle(EntryAction.DEFER, dec, "MOMENTUM_IGNITION", struct, None, object())
    print(f"Policy Action: {policy_dec.action}, Reason: {policy_dec.reason}")
