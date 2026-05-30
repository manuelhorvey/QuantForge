"""Synthetic market data fixture mocks at the yfinance network boundary.

Substitutes ``yfinance.download`` with pre-generated random-walk data
so every code path that calls yfinance (fetch_live, fetch_asset_data,
fetch_asset_ohlcv, macro batch, history, etc.) returns synthetic data
without network I/O.

Usage::

    mock = MockDataFixture(tickers=["EURUSD=X", "USDJPY=X"], n_bars=500)
    mock.install()
    # ... run engine (all yfinance calls return mock data) ...
    mock.uninstall()
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger("benchmark.mock_data")


class MockDataFixture:
    """Generates synthetic OHLCV + macro data and monkeypatches yfinance.download.

    The mock replaces ``yfinance.download`` at the module level so every
    caller — ``fetch_live``, ``fetch_asset_data``, ``fetch_asset_ohlcv``,
    ``_fetch_macro_batch``, ``_fetch_single_series``, ``fetch_history`` —
    transparently receives synthetic data.
    """

    def __init__(self, tickers: list[str], n_bars: int = 500, seed: int = 42):
        self._tickers = list(tickers)
        self._n_bars = n_bars
        self._originals: dict[str, Any] = {}
        self._generate(seed)

    # ── Data generation ──────────────────────────────────────────────

    def _generate(self, seed: int) -> None:
        rng = np.random.RandomState(seed)
        dates_utc = pd.date_range(end="2026-05-29", periods=self._n_bars, freq="D", tz="UTC").normalize()
        dates_et = dates_utc.tz_convert("US/Eastern")

        # Per-ticker OHLCV (stores in yfinance return format: uppercase cols)
        self._ohlcv: dict[str, pd.DataFrame] = {}
        for ticker in self._tickers:
            drift = rng.uniform(-0.0002, 0.0005)
            log_rets = rng.randn(self._n_bars) * 0.012 + drift
            closes = 100.0 * np.exp(np.cumsum(log_rets))
            opens = closes * np.exp(rng.randn(self._n_bars) * 0.002)
            highs = np.maximum(opens, closes) * (1 + np.abs(rng.randn(self._n_bars)) * 0.003)
            lows = np.minimum(opens, closes) * (1 - np.abs(rng.randn(self._n_bars)) * 0.003)
            volumes = rng.randint(500_000, 5_000_000, self._n_bars)

            # yfinance returns US/Eastern tz-aware index
            self._ohlcv[ticker] = pd.DataFrame(
                {
                    "Open": opens,
                    "High": highs,
                    "Low": lows,
                    "Close": closes,
                    "Volume": volumes,
                },
                index=dates_et.copy(),
            )

        # Shared macro series (also US/Eastern yfinance convention)
        vix_raw = 15.0 + np.cumsum(rng.randn(self._n_bars) * 0.5)
        vix_raw = np.clip(vix_raw, 8, 50)
        macro_data = {
            "DX-Y.NYB": 105.0 + np.cumsum(rng.randn(self._n_bars) * 0.05),
            "^VIX": vix_raw,
            "^GSPC": 4500.0 * np.exp(np.cumsum(rng.randn(self._n_bars) * 0.008)),
            "CL=F": 75.0 * np.exp(np.cumsum(rng.randn(self._n_bars) * 0.015)),
            "^TNX": 4.0 + np.cumsum(rng.randn(self._n_bars) * 0.02),
        }
        for t_name, t_close in macro_data.items():
            closes = t_close
            opens = closes * np.exp(rng.randn(self._n_bars) * 0.001)
            highs = np.maximum(opens, closes) * (1 + np.abs(rng.randn(self._n_bars)) * 0.002)
            lows = np.minimum(opens, closes) * (1 - np.abs(rng.randn(self._n_bars)) * 0.002)
            volumes = rng.randint(100_000, 1_000_000, self._n_bars)
            self._ohlcv[t_name] = pd.DataFrame(
                {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
                index=dates_et.copy(),
            )

        # Rate diffs: one column per ticker (UTC index)
        self._rate_diffs = pd.DataFrame(
            {t: rng.randn(self._n_bars) * 0.001 for t in self._tickers},
            index=dates_utc,
        )

    # ── Install / uninstall monkeypatches ────────────────────────────

    def install(self) -> None:
        import yfinance as yf_mod

        import paper_trading.ops.data_fetcher as fetcher_mod

        self._originals["yf_download"] = yf_mod.download
        self._originals["yf_Ticker"] = yf_mod.Ticker
        self._originals["_rate_limit"] = fetcher_mod._rate_limit
        yf_mod.download = self._mock_download
        fetcher_mod._rate_limit = lambda: None

        # Mock Ticker to avoid real-time quote network calls in refresh_price
        _fixture = self

        class _MockFastInfo:
            def get(self, key: str, default: Any = None) -> Any:
                return 100.0 if key == "lastPrice" else default

        class _MockTicker:
            def __init__(self, ticker: str) -> None:
                self._t = ticker
                self.fast_info = _MockFastInfo()

            def history(self, *args: Any, **kwargs: Any) -> pd.DataFrame:
                return _fixture._lookup_ohlcv(self._t)

        yf_mod.Ticker = _MockTicker

    def uninstall(self) -> None:
        import yfinance as yf_mod

        import paper_trading.ops.data_fetcher as fetcher_mod

        if "yf_download" in self._originals:
            yf_mod.download = self._originals["yf_download"]
        if "yf_Ticker" in self._originals:
            yf_mod.Ticker = self._originals["yf_Ticker"]
        if "_rate_limit" in self._originals:
            fetcher_mod._rate_limit = self._originals["_rate_limit"]

    # ── Mock yfinance.download ───────────────────────────────────────

    def _lookup_ohlcv(self, ticker: str) -> pd.DataFrame:
        df = self._ohlcv.get(ticker)
        if df is not None:
            return df.copy()
        for k, v in self._ohlcv.items():
            if ticker in k or k in ticker:
                return v.copy()
        return next(iter(self._ohlcv.values())).copy()

    def _mock_download(
        self,
        tickers: str | list[str],
        period: str | None = None,
        interval: str | None = None,
        group_by: str | None = None,
        auto_adjust: bool | None = None,
        progress: bool = True,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Replacement for ``yfinance.download``.

        Handles:
        - Single ticker string → flat DataFrame (Open/High/Low/Close/Volume)
        - Multiple tickers with ``group_by='ticker'`` → MultiIndex columns
        """
        ticker_list = [tickers] if isinstance(tickers, str) else list(tickers)

        if len(ticker_list) == 1 and group_by != "ticker":
            df = self._lookup_ohlcv(ticker_list[0])
            return df

        # Multi-ticker: build DataFrame with MultiIndex columns
        dfs: dict[str, pd.DataFrame] = {}
        index: pd.Index | None = None
        for t in ticker_list:
            df = self._lookup_ohlcv(t)
            dfs[t] = df[["Open", "High", "Low", "Close", "Volume"]]
            if index is None:
                index = df.index
        if index is None:
            return pd.DataFrame()

        if group_by == "ticker":
            arrays: list[list] = [[], []]
            for t in ticker_list:
                for col in ["Open", "High", "Low", "Close", "Volume"]:
                    arrays[0].append(t)
                    arrays[1].append(col)
            multi_idx = pd.MultiIndex.from_arrays(arrays)
            data = np.column_stack([dfs[t].values for t in ticker_list])
            result = pd.DataFrame(data, index=index, columns=multi_idx)
        else:
            result = pd.concat(dfs.values(), axis=1, keys=ticker_list)

        return result
