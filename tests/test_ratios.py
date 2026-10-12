"""One test per ratio. These are pure functions, so the tests are cheap."""

import pandas as pd
import pytest

from src.ratios import (
    RATIO_COLUMNS,
    build_ratios,
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
    peer_percentile_rank,
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


# --- build_ratios ----------------------------------------------------------


def _annual(rows):
    """rows: (ticker, fiscal_year, concept, value) tuples; every year ends Dec 31."""
    df = pd.DataFrame(rows, columns=["ticker", "fiscal_year", "concept", "value"])
    df["period_end"] = pd.to_datetime(df["fiscal_year"].astype(str) + "-12-31")
    return df


def _full_year(ticker, year, **overrides):
    facts = {
        "revenue": 1000, "gross_profit": 400, "operating_income": 200, "net_income": 100,
        "assets": 500, "assets_current": 300, "liabilities": 300, "liabilities_current": 150,
        "equity": 200, "inventory": 50, "cfo": 180, "capex": 80, "interest_expense": 20,
    }
    facts.update(overrides)
    return [(ticker, year, concept, value) for concept, value in facts.items()]


def test_build_ratios_has_one_row_per_ticker_and_year():
    annual = _annual(_full_year("AAA", 2023) + _full_year("AAA", 2024) + _full_year("BBB", 2024))

    out = build_ratios(annual)

    assert len(out) == 3
    assert set(RATIO_COLUMNS) <= set(out.columns)


@pytest.mark.parametrize(
    ("period_end", "period_year"),
    [("2025-12-31", 2025), ("2025-06-30", 2025), ("2026-01-31", 2025), ("2026-02-01", 2025)],
)
def test_build_ratios_period_year_puts_a_january_year_end_in_the_prior_year(period_end, period_year):
    annual = _annual(_full_year("AAA", 2025))
    annual["period_end"] = pd.Timestamp(period_end)

    out = build_ratios(annual).iloc[0]

    assert out["period_year"] == period_year


def test_build_ratios_computes_each_ratio_from_the_facts():
    out = build_ratios(_annual(_full_year("AAA", 2024))).iloc[0]

    assert out["gross_margin"] == pytest.approx(0.4)
    assert out["net_margin"] == pytest.approx(0.1)
    assert out["roe"] == pytest.approx(0.5)
    assert out["current_ratio"] == pytest.approx(2.0)
    assert out["quick_ratio"] == pytest.approx(250 / 150)
    assert out["debt_to_equity"] == pytest.approx(1.5)
    assert out["interest_coverage"] == pytest.approx(10.0)
    assert out["fcf_margin"] == pytest.approx(0.1)


def test_build_ratios_growth_compares_to_the_prior_fiscal_year():
    annual = _annual(
        _full_year("AAA", 2023, revenue=800, net_income=50)
        + _full_year("AAA", 2024, revenue=1000, net_income=100)
    )

    out = build_ratios(annual).set_index("fiscal_year")

    assert out.loc[2024, "revenue_growth"] == pytest.approx(0.25)
    assert out.loc[2024, "net_income_growth"] == pytest.approx(1.0)
    assert pd.isna(out.loc[2023, "revenue_growth"])


def test_build_ratios_growth_is_blank_when_the_prior_year_is_missing():
    annual = _annual(_full_year("AAA", 2021) + _full_year("AAA", 2024))

    out = build_ratios(annual).set_index("fiscal_year")

    assert pd.isna(out.loc[2024, "revenue_growth"])


def test_build_ratios_leaves_a_ratio_blank_when_its_input_is_missing():
    rows = [r for r in _full_year("AAA", 2024) if r[2] != "gross_profit"]

    out = build_ratios(_annual(rows)).iloc[0]

    assert pd.isna(out["gross_margin"])
    assert out["net_margin"] == pytest.approx(0.1)


def test_build_ratios_blanks_equity_ratios_when_equity_is_negative():
    out = build_ratios(_annual(_full_year("AAA", 2024, equity=-100))).iloc[0]

    assert pd.isna(out["roe"])
    assert pd.isna(out["debt_to_equity"])
    assert pd.isna(out["equity_multiplier"])
    assert out["roa"] == pytest.approx(0.2)


# --- peer_percentile_rank --------------------------------------------------


def _ratio_rows(values, year=2024, column="net_margin"):
    return pd.DataFrame(
        {"ticker": list(values), "period_year": year, column: list(values.values())}
    )


def test_peer_rank_gives_the_highest_value_a_percentile_of_one():
    ratios = _ratio_rows({"AAA": 0.30, "BBB": 0.10, "CCC": 0.20, "DDD": 0.40})

    ranked = peer_percentile_rank(ratios, {"set_one": ["AAA", "BBB", "CCC", "DDD"]})
    by_ticker = ranked.set_index("ticker")["net_margin"]

    assert by_ticker["DDD"] == pytest.approx(1.0)
    assert by_ticker["BBB"] == pytest.approx(0.25)
    assert by_ticker["AAA"] == pytest.approx(0.75)


def test_peer_rank_compares_only_within_the_same_peer_set():
    ratios = _ratio_rows({"A1": 0.50, "A2": 0.10, "A3": 0.30, "B1": 0.90, "B2": 0.80, "B3": 0.85})
    sets = {"first": ["A1", "A2", "A3"], "second": ["B1", "B2", "B3"]}

    by_ticker = peer_percentile_rank(ratios, sets).set_index("ticker")["net_margin"]

    assert by_ticker["A1"] == pytest.approx(1.0)
    assert by_ticker["B1"] == pytest.approx(1.0)
    assert by_ticker["A2"] == pytest.approx(1 / 3)


def test_peer_rank_compares_only_within_the_same_period_year():
    ratios = pd.concat([
        _ratio_rows({"AAA": 0.1, "BBB": 0.2, "CCC": 0.3}, year=2023),
        _ratio_rows({"AAA": 0.5, "BBB": 0.4, "CCC": 0.1}, year=2024),
    ])

    ranked = peer_percentile_rank(ratios, {"s": ["AAA", "BBB", "CCC"]})
    in_2024 = ranked[ranked["period_year"] == 2024].set_index("ticker")["net_margin"]

    assert in_2024["AAA"] == pytest.approx(1.0)
    assert in_2024["BBB"] == pytest.approx(2 / 3)
    assert in_2024["CCC"] == pytest.approx(1 / 3)


def test_peer_rank_skips_a_missing_value_and_ranks_the_rest():
    ratios = _ratio_rows({"AAA": 0.1, "BBB": float("nan"), "CCC": 0.3, "DDD": 0.2})

    by_ticker = peer_percentile_rank(
        ratios, {"s": ["AAA", "BBB", "CCC", "DDD"]}
    ).set_index("ticker")["net_margin"]

    assert pd.isna(by_ticker["BBB"])
    assert by_ticker["CCC"] == pytest.approx(1.0)
    assert by_ticker["AAA"] == pytest.approx(1 / 3)


def test_peer_rank_is_blank_when_fewer_than_three_peers_have_a_value():
    ratios = _ratio_rows({"AAA": 0.1, "BBB": 0.2})

    ranked = peer_percentile_rank(ratios, {"s": ["AAA", "BBB"]})

    assert ranked["net_margin"].isna().all()


def test_peer_rank_labels_each_row_with_its_peer_set():
    ratios = _ratio_rows({"AAA": 0.1, "XXX": 0.2})

    ranked = peer_percentile_rank(ratios, {"first": ["AAA"], "second": ["XXX"]})

    assert dict(zip(ranked["ticker"], ranked["peer_set"])) == {"AAA": "first", "XXX": "second"}
