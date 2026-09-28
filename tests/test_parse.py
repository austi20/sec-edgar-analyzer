"""Parser tests run against a small committed JSON fixture in tests/fixtures/."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.parse import COLUMNS, flatten_company_facts

FIXTURE = Path(__file__).parent / "fixtures" / "companyfacts_sample.json"


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


@pytest.mark.skip(reason="implement with resolve_concepts()")
def test_concept_aliasing_prefers_priority_order():
    ...


@pytest.mark.skip(reason="implement with drop_restatements()")
def test_restatement_keeps_latest_filed():
    ...
