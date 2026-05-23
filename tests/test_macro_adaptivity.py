import pytest
import numpy as np
import pandas as pd
from models.macro_expert_head import MacroExpertHead

def test_macro_expert_adaptive_weight():
    # Setup head with online_weight=True
    head = MacroExpertHead(features=["f1", "f2"], online_weight=True)
    initial_weight = head.current_weight
    
    # 1. Macro outperforms blend (simulated)
    # macro_ret = 0.05, blend_ret = 0.01
    # m_sharpe will be higher
    for _ in range(30):
        head.update_weight(macro_ret=0.05, blend_ret=0.01)
        
    assert head.current_weight > initial_weight
    assert head.current_weight <= 0.65
    
    # 2. Blend outperforms macro
    current = head.current_weight
    for _ in range(100):
        head.update_weight(macro_ret=-0.05, blend_ret=0.05)
        
    assert head.current_weight < current
    assert head.current_weight >= 0.25

def test_macro_expert_weight_disabled():
    head = MacroExpertHead(features=["f1", "f2"], online_weight=False)
    initial_weight = head.current_weight
    
    for _ in range(50):
        head.update_weight(macro_ret=0.1, blend_ret=0.0)
        
    assert head.current_weight == initial_weight
