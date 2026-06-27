from typing import Final

SELL_ONLY_ASSETS: Final[frozenset[str]] = frozenset(
    {
        "CADCHF",
        "ES",
        "NQ",
        "NZDCHF",
        "EURAUD",
    }
)

SPREAD_TIER_BPS: Final[dict[str, float]] = {
    "fx_major": 10.0,
    "fx_cross": 20.0,
    "indices": 15.0,
    "metals": 20.0,
}

SPREAD_GATE_STALENESS_SECS: Final[int] = 300
