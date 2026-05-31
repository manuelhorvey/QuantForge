import json
import os
from datetime import datetime

import pytz

from features.fxstreet_fetcher import confirm_pending_narrative, get_narrative_status
from paper_trading.api.common import _STORE, CONFIDENCE_PATH, LOG_PATH, cache_get, cache_set, route_cache_key
from paper_trading.api.read_models import DashboardReadModels
from paper_trading.governance.health import compute_all as _compute_health_all
from paper_trading.governance.health import get_latest as _get_health_latest
from paper_trading.governance.risk import get_latest as _get_risk_latest

ET = pytz.timezone("US/Eastern")
_READ_MODELS = DashboardReadModels(_STORE, CONFIDENCE_PATH)


def _json(data, *, indent: int | None = 2) -> str:
    return json.dumps(data, indent=indent, default=str)


def _cache_route(path: str, query: dict, data: str, *, query_aware: bool = False) -> str:
    cache_set(route_cache_key(path, query) if query_aware else path, data)
    return data


def _cached(path: str) -> str | None:
    return cache_get(path)


def handle_state(path: str, query: dict) -> str:
    cached = _cached(path)
    if cached is not None:
        return cached
    return _cache_route(path, query, _json(_READ_MODELS.state()))


def handle_trades(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.trades(query), indent=None), query_aware=True)


def handle_equity_history(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.equity_history(), indent=None))


def handle_confidence(path: str, query: dict) -> str:
    cached = _cached(path)
    if cached is not None:
        return cached
    return _cache_route(path, query, _json(_READ_MODELS.confidence()))


def handle_volatility(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.volatility()))


def handle_logs(path: str, query: dict) -> str:
    try:
        with open(LOG_PATH) as f:
            lines = f.readlines()
        boundary = None
        for i in range(len(lines) - 1, -1, -1):
            if "Server stopped." in lines[i]:
                boundary = i + 1
                break
        return "".join(lines[boundary:][-200:]) if boundary is not None else "".join(lines[-200:])
    except FileNotFoundError:
        return "[no log file yet]"


def handle_risk(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_get_risk_latest()))


def handle_risk_asset(path: str, query: dict) -> tuple[str, int]:
    asset = path[len("/risk/") : -len(".json")]
    signal = _get_risk_latest(asset)
    if signal is not None:
        return _json(signal), 200
    return _json({"error": f"No risk signal for {asset}", "asset": asset}, indent=None), 404


def handle_shadow_actions(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.shadow_actions() or {}))


def handle_shadow_actions_asset(path: str, query: dict) -> tuple[str, int]:
    asset = path[len("/shadow-actions/") : -len(".json")]
    action = _READ_MODELS.shadow_action(asset)
    if action is not None:
        return _json(action), 200
    return _json({"error": f"No shadow action for {asset}", "asset": asset}, indent=None), 404


def handle_health(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_compute_health_all()))


def handle_health_asset(path: str, query: dict) -> tuple[str, int]:
    asset = path[len("/health/") : -len(".json")]
    signal = _get_health_latest(asset)
    if signal is not None:
        return _json(signal), 200
    return _json({"error": f"No health score for {asset}", "asset": asset}, indent=None), 404


def handle_governance(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.governance()))


def handle_risk_parity(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.risk_parity() or {}))


def handle_narrative(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(get_narrative_status()))


def handle_liquidity(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.liquidity()))


def handle_psi(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.psi()))


def handle_trade_outcomes(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.trade_outcomes()))


def handle_weekly_review(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.weekly_review()))


def handle_ping(path: str, query: dict) -> str:
    return _json({"status": "ok"})


def handle_narrative_confirm(body: bytes) -> tuple[str, int]:
    ok = confirm_pending_narrative()
    if ok:
        return _json({"status": "confirmed", "message": "Narrative confirmed"}), 200
    return _json({"status": "error", "message": "No pending narrative to confirm"}), 400


def handle_weekly_review_acknowledge(body: bytes) -> tuple[str, int]:
    now = datetime.now(tz=ET).isoformat()
    entry = {"acknowledged_at": now}
    review_log_path = _STORE.review_log_path
    existing = []
    if os.path.exists(review_log_path):
        try:
            with open(review_log_path) as f:
                existing = json.load(f)
        except Exception:
            existing = []
    existing.append(entry)
    with open(review_log_path, "w") as f:
        json.dump(existing, f, indent=2)
    return _json({"status": "ok", "acknowledged_at": now}), 200


def handle_attribution_trades(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.attribution_trades(query)), query_aware=True)


def handle_attribution_summary(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.attribution_summary(query)), query_aware=True)


def handle_execution_quality(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.execution_quality(query)), query_aware=True)


def handle_execution_slippage(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.execution_slippage(query)), query_aware=True)


def handle_shadow_trades_route(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.shadow_trades(query)), query_aware=True)


def handle_shadow_summary(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.shadow_summary(query)), query_aware=True)


def handle_analytics_snapshot(path: str, query: dict) -> str:
    return _json(_READ_MODELS.analytics_snapshot())


def handle_attribution_waterfall(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.attribution_waterfall(query)), query_aware=True)


def handle_archetype_stats(path: str, query: dict) -> str:
    return _cache_route(path, query, _json(_READ_MODELS.archetype_stats(query)), query_aware=True)


GET_ROUTES: dict[str, tuple] = {
    "/state.json": (handle_state, False),
    "/trades.json": (handle_trades, False),
    "/equity_history.json": (handle_equity_history, False),
    "/confidence.json": (handle_confidence, False),
    "/volatility.json": (handle_volatility, False),
    "/logs": (handle_logs, True),
    "/risk.json": (handle_risk, False),
    "/shadow-actions": (handle_shadow_actions, False),
    "/health.json": (handle_health, False),
    "/governance.json": (handle_governance, False),
    "/risk-parity.json": (handle_risk_parity, False),
    "/narrative.json": (handle_narrative, False),
    "/liquidity.json": (handle_liquidity, False),
    "/psi.json": (handle_psi, False),
    "/trade-outcomes.json": (handle_trade_outcomes, False),
    "/weekly-review.json": (handle_weekly_review, False),
    "/attribution/trades.json": (handle_attribution_trades, False),
    "/attribution/summary.json": (handle_attribution_summary, False),
    "/execution/quality.json": (handle_execution_quality, False),
    "/execution/slippage.json": (handle_execution_slippage, False),
    "/shadow/trades.json": (handle_shadow_trades_route, False),
    "/shadow/summary.json": (handle_shadow_summary, False),
    "/archetype/stats.json": (handle_archetype_stats, False),
    "/attribution/waterfall.json": (handle_attribution_waterfall, False),
    "/analytics/snapshot.json": (handle_analytics_snapshot, False),
    "/ping": (handle_ping, False),
}

GET_ROUTES_PREFIX: list[tuple[str, object, bool]] = [
    ("/risk/", handle_risk_asset, False),
    ("/shadow-actions/", handle_shadow_actions_asset, False),
    ("/health/", handle_health_asset, False),
]

POST_ROUTES: dict[str, object] = {
    "/narrative/confirm": handle_narrative_confirm,
    "/weekly-review/acknowledge": handle_weekly_review_acknowledge,
}
