"""One test per ratio. These are pure functions, so the tests are cheap."""

import pytest

from src.ratios import (
    asset_turnover,
    current_ratio,
    debt_to_equity,
    dupont,
    equity_multiplier,
    fcf_margin,
    free_cash_flow,
    gross_margin,
    interest_coverage,
    net_margin,
    operating_margin,
    quick_ratio,
    return_on_assets,
    return_on_equity,
    yoy_growth,
)


def test_gross_margin_is_gross_profit_over_revenue():
    assert gross_margin(40, 200) == pytest.approx(0.2)


def test_operating_margin_is_operating_income_over_revenue():
    assert operating_margin(30, 120) == pytest.approx(0.25)


def test_return_on_assets_is_net_income_over_assets():
    assert return_on_assets(15, 300) == pytest.approx(0.05)


def test_current_ratio_is_current_assets_over_current_liabilities():
    assert current_ratio(150, 100) == pytest.approx(1.5)


def test_quick_ratio_strips_inventory_from_current_assets():
    assert quick_ratio(150, 50, 80) == pytest.approx(1.25)


def test_debt_to_equity_is_liabilities_over_equity():
    assert debt_to_equity(300, 200) == pytest.approx(1.5)


def test_interest_coverage_is_operating_income_over_interest():
    assert interest_coverage(90, 15) == pytest.approx(6.0)


def test_free_cash_flow_is_cfo_minus_capex():
    assert free_cash_flow(500, 120) == pytest.approx(380)


def test_free_cash_flow_goes_negative_when_capex_exceeds_cfo():
    assert free_cash_flow(100, 140) == pytest.approx(-40)


def test_fcf_margin_is_free_cash_flow_over_revenue():
    assert fcf_margin(500, 100, 2000) == pytest.approx(0.2)


def test_yoy_growth_is_change_over_prior():
    assert yoy_growth(120, 100) == pytest.approx(0.2)


def test_yoy_growth_is_negative_on_a_decline():
    assert yoy_growth(75, 100) == pytest.approx(-0.25)


def test_yoy_growth_from_a_negative_prior_rises_when_loss_shrinks():
    # loss shrank from -100 to -40, so growth is positive
    assert yoy_growth(-40, -100) == pytest.approx(0.6)


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
