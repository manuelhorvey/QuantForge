from research.risk.synthetic_stress import adjust_injection_rate_for_crisis_density


def test_lowers_injection_when_crisis_density_high():
    rate = adjust_injection_rate_for_crisis_density(
        crisis_fraction=0.10,
        base_rate=0.25,
        target_crisis_fraction=0.05,
    )
    assert rate == 0.0


def test_keeps_injection_when_crisis_sparse():
    rate = adjust_injection_rate_for_crisis_density(
        crisis_fraction=0.01,
        base_rate=0.25,
        target_crisis_fraction=0.05,
    )
    assert rate > 0.0
