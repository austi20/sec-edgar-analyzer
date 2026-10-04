"""One test per ratio. These are pure functions, so the tests are cheap."""

import pytest

from src.ratios import (
    asset_turnover,
    dupont,
    equity_multiplier,
    net_margin,
    return_on_equity,
)


def test_net_margin_is_net_income_over_revenue():
    assert net_margin(25, 100) == pytest.approx(0.25)


def test_asset_turnover_is_revenue_over_assets():
    assert asset_turnover(200, 100) == pytest.approx(2.0)


def test_equity_multiplier_is_assets_over_equity():
    assert equity_multiplier(100, 25) == pytest.approx(4.0)


def test_return_on_equity_is_net_income_over_equity():
    assert return_on_equity(10, 50) == pytest.approx(0.2)


def test_dupont_returns_the_three_drivers_and_roe():
    # four different inputs, so feeding any driver the wrong one changes its value
    parts = dupont(net_income=30, revenue=300, assets=150, equity=60)

    assert parts == {
        "net_margin": pytest.approx(0.1),
        "asset_turnover": pytest.approx(2.0),
        "equity_multiplier": pytest.approx(2.5),
        "roe": pytest.approx(0.5),
    }


@pytest.mark.parametrize(
    ("net_income", "revenue", "assets", "equity"),
    [
        (30, 300, 150, 60),
        (-12, 80, 200, 90),
        (15_000, 150_000, 70_000, -1_500),
    ],
    ids=["profitable", "loss-making", "negative-equity"],
)
def test_dupont_components_multiply_to_roe(net_income, revenue, assets, equity):
    parts = dupont(net_income, revenue, assets, equity)
    direct = return_on_equity(net_income, equity)

    product = parts["net_margin"] * parts["asset_turnover"] * parts["equity_multiplier"]
    assert product == pytest.approx(direct, rel=1e-12)
    assert parts["roe"] == pytest.approx(direct, rel=1e-12)
