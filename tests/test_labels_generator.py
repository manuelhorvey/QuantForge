import pytest
import os
import pandas as pd
import numpy as np
from labels.generator import LabelGenerator
from features.registry import FEATURE_REGISTRY
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_registry():
    mock_contract = MagicMock()
    mock_contract.name = "TEST"
    mock_contract.ticker = "TEST"
    mock_contract.label_version = "v1_test"
    mock_contract.label_params = {
        "pt_sl": [2, 2],
        "vertical_barrier": 20,
        "vol_method": "ewm_100"
    }
    return {"TEST": mock_contract}

def test_label_generator_init(tmp_path):
    data_dir = str(tmp_path / "data")
    gen = LabelGenerator(data_dir=data_dir)
    assert gen.data_dir == data_dir
    assert os.path.exists(gen.processed_dir)

def test_generate_asset_labels(tmp_path, sample_price_data):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True)
    
    # Save sample data
    sample_price_data.to_parquet(raw_dir / "TEST_1d.parquet")
    
    gen = LabelGenerator(data_dir=str(data_dir))
    
    mock_contract = MagicMock()
    mock_contract.name = "TEST"
    mock_contract.ticker = "TEST"
    mock_contract.label_version = "v1_test"
    mock_contract.label_params = {
        "pt_sl": [2, 2],
        "vertical_barrier": 20
    }
    
    out_path = gen.generate_asset_labels(mock_contract)
    
    assert os.path.exists(out_path)
    df = pd.read_parquet(out_path)
    assert "label_new" in df.columns
    assert "label_shadow" in df.columns
    assert df.attrs["label_version"] == "v1_test"

def test_generate_asset_labels_with_atr(tmp_path, sample_price_data):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True)
    sample_price_data.to_parquet(raw_dir / "TEST_1d.parquet")
    
    gen = LabelGenerator(data_dir=str(data_dir))
    
    mock_contract = MagicMock()
    mock_contract.name = "TEST"
    mock_contract.ticker = "TEST"
    mock_contract.label_version = "v1_atr"
    mock_contract.label_params = {
        "pt_sl": [2, 2],
        "vertical_barrier": 20,
        "vol_method": "atr",
        "atr_period": 14
    }
    
    out_path = gen.generate_asset_labels(mock_contract)
    assert os.path.exists(out_path)
    df = pd.read_parquet(out_path)
    assert df.attrs["vol_method"] == "atr_ohlc"

def test_generate_all(tmp_path, sample_price_data):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True)
    
    # We only provide data for one asset from the registry to keep it fast
    # and we'll mock the registry to only have that asset
    sample_price_data.to_parquet(raw_dir / "BTC_1d.parquet")
    
    gen = LabelGenerator(data_dir=str(data_dir))
    
    with patch("labels.generator.FEATURE_REGISTRY") as mock_reg:
        mock_contract = MagicMock()
        mock_contract.name = "BTC"
        mock_contract.ticker = "BTC-USD"
        mock_contract.label_version = "v_btc"
        mock_contract.label_params = {"pt_sl": [1.5, 0.5], "vertical_barrier": 20}
        
        mock_reg.items.return_value = [("BTC-USD", mock_contract)]
        
        results = gen.generate_all()
        assert "BTC-USD" in results
        assert os.path.exists(results["BTC-USD"])

def test_generate_asset_labels_not_found(tmp_path):
    gen = LabelGenerator(data_dir=str(tmp_path))
    mock_contract = MagicMock()
    mock_contract.name = "MISSING"
    mock_contract.ticker = "MISSING"
    
    with pytest.raises(FileNotFoundError):
        gen.generate_asset_labels(mock_contract)
