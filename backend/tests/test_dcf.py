import pytest

from gufu.metrics.dcf import choose_growth, dcf_two_stage, graham_number, margin_of_safety


def explicit_dcf(base, g1, g2, r, n1, n2):
    v, cf = 0.0, base
    for t in range(1, n1 + 1):
        cf *= 1 + g1
        v += cf / (1 + r) ** t
    for t in range(n1 + 1, n1 + n2 + 1):
        cf *= 1 + g2
        v += cf / (1 + r) ** t
    return v


def test_closed_form_matches_explicit_sum():
    for base, g1 in ((5.0, 0.12), (2.5, 0.0), (10.0, 0.10)):
        assert dcf_two_stage(base, g1, 0.04, 0.10, 10, 10) == pytest.approx(explicit_dcf(base, g1, 0.04, 0.10, 10, 10))


def test_dcf_edge_cases():
    assert dcf_two_stage(None, 0.1) is None
    assert dcf_two_stage(-1.0, 0.1) is None
    assert dcf_two_stage(1.0, 0.10, 0.10, 0.10, 10, 10) == pytest.approx(20.0)  # growth == discount


def test_growth_clamp_and_graham():
    assert choose_growth(None, 0.5) == 0.20
    assert choose_growth(-0.1) == 0.0
    assert choose_growth(None, None) == 0.06
    assert graham_number(4.0, 10.0) == pytest.approx(30.0)  # sqrt(22.5*4*10)=sqrt(900)
    assert graham_number(-1.0, 9.0) is None
    assert margin_of_safety(120.0, 90.0) == pytest.approx(0.25)
