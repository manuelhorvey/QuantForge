import pytest
from paper_trading.engine import (
    flatten, norm_index, CONFIG, HALT,
    XLF_FEATURES, BTC_FEATURES, PAPER_PORTFOLIO,
)


class TestHelpers:
    def test_flatten_single_level(self):
        import pandas as pd
        df = pd.DataFrame({"Close": [100, 101]})
        result = flatten(df)
        assert "close" in result.columns
        assert "Close" not in result.columns

    def test_flatten_multi_index(self):
        import pandas as pd
        arrays = [["Close", "High"], ["XLF", "XLF"]]
        cols = pd.MultiIndex.from_arrays(arrays, names=["Price", "Ticker"])
        df = pd.DataFrame([[100, 101], [102, 103]], columns=cols)
        result = flatten(df)
        assert "close" in result.columns

    def test_norm_index_already_utc(self):
        import pandas as pd
        df = pd.DataFrame({"close": [100]}, index=pd.DatetimeIndex(["2020-01-01"], tz="UTC"))
        result = norm_index(df)
        assert result.index.tz is not None

    def test_norm_index_naive(self):
        import pandas as pd
        df = pd.DataFrame({"close": [100]}, index=pd.DatetimeIndex(["2020-01-01"]))
        result = norm_index(df)
        assert result.index.tz is not None


class TestConfig:
    def test_has_expected_keys(self):
        assert "capital" in CONFIG
        assert "position_size" in CONFIG
        assert "rebalance" in CONFIG
        assert "retrain_freq" in CONFIG
        assert "retrain_window" in CONFIG

    def test_halt_has_expected_keys(self):
        assert "drawdown" in HALT
        assert "monthly_pf" in HALT
        assert "signal_drought" in HALT
        assert "prob_drift" in HALT

    def test_xlf_features(self):
        assert len(XLF_FEATURES) == 4
        assert "rate_diff" in XLF_FEATURES

    def test_btc_features(self):
        assert len(BTC_FEATURES) == 4
        assert "rate_diff" in BTC_FEATURES

    def test_paper_portfolio_structure(self):
        assert "XLF" in PAPER_PORTFOLIO
        assert "BTC" in PAPER_PORTFOLIO
        assert "NZDJPY" in PAPER_PORTFOLIO
        assert PAPER_PORTFOLIO["XLF"]["alloc"] == 0.40
        assert PAPER_PORTFOLIO["BTC"]["alloc"] == 0.35
        assert PAPER_PORTFOLIO["NZDJPY"]["alloc"] == 0.25
