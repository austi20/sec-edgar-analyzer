"""Parser tests run against a small committed JSON fixture in tests/fixtures/."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.parse import (
    COLUMNS,
    drop_restatements,
    flatten_company_facts,
    resolve_concepts,
)

FIXTURE = Path(__file__).parent / "fixtures" / "companyfacts_sample.json"
REVENUE_PREFERRED = "RevenueFromContractWithCustomerExcludingAssessedTax"


@pytest.fixture
def facts() -> dict:
    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)


def test_flatten_has_one_row_per_us_gaap_fact(facts):
    df = flatten_company_facts(facts, "HD")

    assert list(df.columns) == COLUMNS
    # 3 revenue + 2 assets + 1 payables + 1 EPS; the dei fact is skipped
    assert len(df) == 7
    assert set(df["ticker"]) == {"HD"}
    assert "EntityCommonStockSharesOutstanding" not in set(df["concept"])


def test_flatten_keeps_fields_from_the_filing(facts):
    df = flatten_company_facts(facts, "HD")
    row = df[(df["concept"] == "Revenues") & (df["form"] == "10-K")].iloc[0]

    assert row["unit"] == "USD"
    assert row["fiscal_year"] == 2009
    assert row["fiscal_period"] == "FY"
    assert row["period_start"] == pd.Timestamp("2007-01-29")
    assert row["period_end"] == pd.Timestamp("2008-02-03")
    assert row["filed"] == pd.Timestamp("2010-03-25")
    assert row["value"] == 77349000000


def test_flatten_separates_six_month_and_three_month_values(facts):
    df = flatten_company_facts(facts, "HD")
    q2 = df[(df["concept"] == "Revenues") & (df["fiscal_period"] == "Q2")]

    # same filing, same period end, different durations
    assert q2["period_end"].nunique() == 1
    assert sorted(q2["period_start"]) == [pd.Timestamp("2008-02-04"), pd.Timestamp("2008-05-05")]


def test_flatten_handles_instants_units_and_missing_fiscal_year(facts):
    df = flatten_company_facts(facts, "HD")

    assets = df[df["concept"] == "Assets"]
    assert assets["period_start"].isna().all()

    eps = df[df["concept"] == "EarningsPerShareBasic"].iloc[0]
    assert eps["unit"] == "USD/shares"
    assert eps["value"] == 2.38

    payables = df[df["concept"] == "AccountsPayableCurrent"].iloc[0]
    assert payables["form"] == "8-K"
    assert pd.isna(payables["fiscal_year"])
    assert pd.isna(payables["fiscal_period"])


def make_facts(*rows: dict) -> pd.DataFrame:
    """flatten_company_facts-shaped frame; each row overrides the defaults."""
    defaults = {
        "ticker": "HD",
        "unit": "USD",
        "fiscal_year": 2020,
        "fiscal_period": "FY",
        "form": "10-K",
        "period_start": pd.Timestamp("2019-02-04"),
        "period_end": pd.Timestamp("2020-02-02"),
        "filed": pd.Timestamp("2020-03-25"),
    }
    return pd.DataFrame([{**defaults, **row} for row in rows], columns=COLUMNS)


def test_concept_aliasing_prefers_priority_order():
    # top-priority tag is listed last, so "first row wins" would fail
    df = make_facts(
        {"concept": "Revenues", "value": 100},
        {"concept": "SalesRevenueNet", "value": 80},
        {"concept": REVENUE_PREFERRED, "value": 90},
    )

    out = resolve_concepts(df)

    assert list(out["concept"]) == ["revenue"]
    assert list(out["value"]) == [90]


def test_concept_aliasing_falls_back_per_period():
    # a filer that switches tags mid-history must keep one unbroken series
    old = {
        "concept": "SalesRevenueNet",
        "value": 70,
        "period_start": pd.Timestamp("2017-01-30"),
        "period_end": pd.Timestamp("2018-01-28"),
    }
    new = {"concept": REVENUE_PREFERRED, "value": 90}

    out = resolve_concepts(make_facts(old, new))

    assert list(out["concept"]) == ["revenue", "revenue"]
    assert sorted(out["value"]) == [70, 90]


def test_resolve_concepts_drops_concepts_outside_the_schema(facts):
    out = resolve_concepts(flatten_company_facts(facts, "HD"))

    assert list(out.columns) == COLUMNS
    # EarningsPerShareBasic and AccountsPayableCurrent have no internal name
    assert set(out["concept"]) == {"revenue", "assets"}


def test_resolve_concepts_keeps_instants_that_have_no_period_start(facts):
    out = resolve_concepts(flatten_company_facts(facts, "HD"))

    assets = out[out["concept"] == "assets"]
    # both 10-Q rows survive: collapsing them is drop_restatements' job
    assert len(assets) == 2
    assert assets["period_start"].isna().all()


@pytest.mark.parametrize("newest_first", [False, True], ids=["oldest-first", "newest-first"])
def test_restatement_keeps_latest_filed(newest_first):
    original = {"concept": "Revenues", "value": 100, "filed": pd.Timestamp("2020-03-25")}
    restated = {"concept": "Revenues", "value": 110, "filed": pd.Timestamp("2021-03-24")}
    rows = [restated, original] if newest_first else [original, restated]

    out = drop_restatements(make_facts(*rows))

    assert list(out["value"]) == [110]


def test_drop_restatements_keeps_quarter_and_year_to_date_sharing_a_period_end(facts):
    out = drop_restatements(flatten_company_facts(facts, "HD"))

    q2 = out[(out["concept"] == "Revenues") & (out["fiscal_period"] == "Q2")]
    # same filing date, same period_end; only period_start tells them apart
    assert sorted(q2["value"]) == [20990000000, 38897000000]


def test_drop_restatements_collapses_a_balance_sheet_date_reported_twice(facts):
    out = drop_restatements(flatten_company_facts(facts, "HD"))

    assets = out[out["concept"] == "Assets"]
    assert len(assets) == 1
    assert assets.iloc[0]["filed"] == pd.Timestamp("2009-12-03")


@pytest.mark.parametrize(("column", "other"), [("ticker", "WMT"), ("unit", "CAD")])
def test_drop_restatements_never_merges_across_tickers_or_units(column, other):
    df = make_facts(
        {"concept": "Revenues", "value": 1},
        {"concept": "Revenues", "value": 2, column: other},
    )

    assert len(drop_restatements(df)) == 2


@pytest.mark.parametrize(
    "steps",
    [(resolve_concepts, drop_restatements), (drop_restatements, resolve_concepts)],
    ids=["resolve-first", "drop-first"],
)
def test_alias_priority_beats_recency_but_latest_filing_wins_within_an_alias(steps):
    df = make_facts(
        {"concept": REVENUE_PREFERRED, "value": 90, "filed": pd.Timestamp("2020-03-25")},
        # restated version of the preferred tag
        {"concept": REVENUE_PREFERRED, "value": 95, "filed": pd.Timestamp("2021-03-24")},
        # filed last, but a lower-priority tag
        {"concept": "SalesRevenueNet", "value": 80, "filed": pd.Timestamp("2022-03-23")},
    )

    for step in steps:
        df = step(df)

    assert list(df["value"]) == [95]
