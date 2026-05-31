import logging
from datetime import datetime

import pandas as pd
import pytz

logger = logging.getLogger("quantforge.governance_service")

ET = pytz.timezone("US/Eastern")


class GovernanceService:
    def __init__(self, asset):
        self.asset = asset

    def set_narrative_state(self, narr) -> None:
        self.asset.governance.set_narrative_state(narr)

    def refresh_liquidity(self, df) -> None:
        self.asset.governance.refresh_liquidity(df)

    def update_validity(self, halt: dict | None = None):
        asset = self.asset
        halt = asset.check_halt_conditions() if halt is None else halt
        score = 0.80
        if not halt["drawdown_ok"]:
            score -= 0.25
        if not halt["monthly_pf_ok"]:
            score -= 0.20
        if not halt["drought_ok"]:
            score -= 0.15
        if not halt["drift_ok"]:
            score -= 0.15
        if not halt.get("liquidity_ok", True):
            score -= 0.10

        if asset._last_stability is not None:
            penalty = asset._last_stability.penalty
            if penalty < 0:
                logger.info(
                    "%s stability penalty: %.3f (jaccard=%.3f, spearman=%.3f)",
                    asset.name,
                    penalty,
                    asset._last_stability.jaccard_top_10,
                    asset._last_stability.spearman_rank_corr,
                )
                score += penalty

        if asset._last_psi_drift is not None and asset._last_psi_drift.penalty < 0:
            psi_p = asset._last_psi_drift.penalty
            logger.info(
                "%s PSI drift penalty: %.3f (worst=%s, moderate=%d, severe=%d)",
                asset.name,
                psi_p,
                asset._last_psi_drift.worst_classification,
                asset._last_psi_drift.moderate_count,
                asset._last_psi_drift.severe_count,
            )
            score += psi_p

        score = max(0.0, min(1.0, score))
        result = asset.validity_sm.transition(score, pd.Timestamp.now(tz=ET))
        result["feature_stability"] = {
            "jaccard_top_10": asset._last_stability.jaccard_top_10 if asset._last_stability else None,
            "spearman_rank_corr": asset._last_stability.spearman_rank_corr if asset._last_stability else None,
            "penalty_applied": asset._last_stability.penalty if asset._last_stability else 0.0,
        }
        result["psi_drift"] = {
            "worst_classification": asset._last_psi_drift.worst_classification if asset._last_psi_drift else "NO_DRIFT",
            "moderate_count": asset._last_psi_drift.moderate_count if asset._last_psi_drift else 0,
            "severe_count": asset._last_psi_drift.severe_count if asset._last_psi_drift else 0,
            "penalty_applied": asset._last_psi_drift.penalty if asset._last_psi_drift else 0.0,
        }
        return result

    def check_halt_conditions(self, metrics: dict | None = None):
        asset = self.asset
        metrics = asset.get_metrics() if metrics is None else metrics
        dd = metrics.get("drawdown", 0) / 100
        if pd.isna(dd):
            dd = 0
        hc = asset.halt_config
        hard_reasons = []
        soft_warnings = []
        if dd <= hc["drawdown"]:
            hard_reasons.append(f"DD {metrics['drawdown']:.1f}% <= {hc['drawdown'] * 100:.0f}%")
        mpf = metrics.get("monthly_pf")
        if mpf is not None and not pd.isna(mpf) and mpf < hc["monthly_pf"]:
            hard_reasons.append(f"PF {mpf:.2f} < {hc['monthly_pf']:.2f}")
        drought_ok = True
        drought_days = hc.get("signal_drought", 30)
        if asset.last_signal_date is not None:
            days_since = (datetime.now(tz=ET).date() - pd.Timestamp(asset.last_signal_date).date()).days
            if days_since > drought_days:
                hard_reasons.append(f"Signal drought: {days_since}d > {drought_days}d")
                drought_ok = False
        drift_ok = True
        if len(asset.prob_history) >= 3:
            prob_drift_limit = hc.get("prob_drift", 0.25)
            mean_conf = metrics.get("mean_confidence", 0) / 100
            if pd.isna(mean_conf):
                mean_conf = 0
            drift = abs(mean_conf - asset.expected_prob_conf)
            if drift > prob_drift_limit:
                hard_reasons.append(f"Confidence drift: {drift:.3f} > {prob_drift_limit:.2f}")
                drift_ok = False

        narrative_ok = True
        narr_warnings = asset.governance.narrative_warnings()
        if narr_warnings:
            soft_warnings.extend(narr_warnings)

        liquidity_ok = True
        liq_warnings = asset.governance.liquidity_warnings()
        if liq_warnings:
            hard_reasons.extend(liq_warnings)
            if asset.governance._liquidity_halted:
                liquidity_ok = False

        psi_ok = True
        if asset._last_psi_drift is not None and not asset._last_psi_drift.psi_ok:
            hard_reasons.append(
                f"PSI drift SEVERE on {asset._last_psi_drift.severe_count} features "
                f"(worst={asset._last_psi_drift.worst_classification})"
            )
            psi_ok = False

        halted = len(hard_reasons) > 0
        return {
            "halted": halted,
            "reasons": [*hard_reasons, *soft_warnings],
            "hard_reasons": hard_reasons,
            "soft_warnings": soft_warnings,
            "drawdown_ok": dd > hc["drawdown"],
            "monthly_pf_ok": mpf is None or pd.isna(mpf) or mpf >= hc["monthly_pf"],
            "drought_ok": drought_ok,
            "drift_ok": drift_ok,
            "narrative_ok": narrative_ok,
            "liquidity_ok": liquidity_ok,
            "psi_ok": psi_ok,
        }
