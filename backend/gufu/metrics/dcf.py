"""Intrinsic value models: Graham number and a two-stage discounted cash flow."""

from __future__ import annotations

import math

DEFAULT_DISCOUNT = 0.10
DEFAULT_TERMINAL_GROWTH = 0.04
DEFAULT_STAGE1_YEARS = 10
DEFAULT_STAGE2_YEARS = 10
GROWTH_FLOOR = 0.0
GROWTH_CAP = 0.20


def graham_number(eps: float | None, bvps: float | None) -> float | None:
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(22.5 * eps * bvps)


def dcf_two_stage(
    base: float | None,
    g1: float,
    g2: float = DEFAULT_TERMINAL_GROWTH,
    r: float = DEFAULT_DISCOUNT,
    n1: int = DEFAULT_STAGE1_YEARS,
    n2: int = DEFAULT_STAGE2_YEARS,
) -> float | None:
    """Present value of `base` growing at g1 for n1 years, then g2 for n2 years, discounted at r.

    Closed form: with x = (1+g1)/(1+r) and y = (1+g2)/(1+r),
      V = base·x(1−x^n1)/(1−x) + base·x^n1·y(1−y^n2)/(1−y)
    """
    if base is None or base <= 0 or r <= -1:
        return None
    x = (1 + g1) / (1 + r)
    y = (1 + g2) / (1 + r)
    stage1 = base * n1 if abs(1 - x) < 1e-12 else base * x * (1 - x**n1) / (1 - x)
    stage2_base = base * x**n1
    stage2 = stage2_base * n2 if abs(1 - y) < 1e-12 else stage2_base * y * (1 - y**n2) / (1 - y)
    return stage1 + stage2


def choose_growth(*candidates: float | None, default: float = 0.06) -> float:
    for c in candidates:
        if c is not None:
            return min(max(c, GROWTH_FLOOR), GROWTH_CAP)
    return default


def margin_of_safety(value: float | None, price: float | None) -> float | None:
    if value is None or price is None or value <= 0:
        return None
    return (value - price) / value
