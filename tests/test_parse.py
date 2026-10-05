"""Parser tests run against a small committed JSON fixture in tests/fixtures/."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.parse import (
    ANNUAL_DAYS,
    ANNUAL_FORMS,
    COLUMNS,
    QUARTER_DAYS,
    QUARTERLY_FORMS,
    build_table,
    drop_restatements,
    filter_form,
    flatten_company_facts,
    label_fiscal_periods,
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


# 13 week quarter inside a Q2 10-Q
QUARTER = {
    "form": "10-Q",
    "fiscal_period": "Q2",
    "period_start": pd.Timestamp("2019-05-06"),
    "period_end": pd.Timestamp("2019-08-04"),
    "filed": pd.Timestamp("2019-09-01"),
}


@pytest.mark.parametrize(
    ("forms", "days", "kept"),
    [(ANNUAL_FORMS, ANNUAL_DAYS, ["10-K", "10-K/A"]), (QUARTERLY_FORMS, QUARTER_DAYS, ["10-Q", "10-Q/A"])],
    ids=["annual", "quarterly"],
)
def test_filter_form_keeps_only_the_requested_forms(forms, days, kept):
    # instants, so duration plays no part here
    df = make_facts(
        *[{"concept": "assets", "value": 1, "form": form, "period_start": pd.NaT}
          for form in ["10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "DEF 14A"]]
    )

    out = filter_form(df, forms, days)

    assert sorted(out["form"]) == kept


@pytest.mark.parametrize("start", ["2019-02-04", "2019-01-28"], ids=["52-week", "53-week"])
def test_filter_form_annual_keeps_full_years_and_drops_a_quarter_tagged_in_the_10k(start):
    df = make_facts(
        {"concept": "revenue", "value": 100, "period_start": pd.Timestamp(start)},
        {"concept": "revenue", "value": 25, "period_start": pd.Timestamp("2019-11-04")},
    )

    out = filter_form(df, ANNUAL_FORMS, ANNUAL_DAYS)

    assert list(out["value"]) == [100]


def test_filter_form_quarterly_drops_year_to_date():
    df = make_facts(
        {**QUARTER, "concept": "revenue", "value": 30},
        {**QUARTER, "concept": "revenue", "value": 60, "period_start": pd.Timestamp("2019-02-04")},
    )

    out = filter_form(df, QUARTERLY_FORMS, QUARTER_DAYS)

    assert list(out["value"]) == [30]


def test_label_moves_a_comparative_to_the_year_it_was_reported_for():
    fy2022 = {
        "concept": "revenue",
        "value": 157,
        "fiscal_year": 2022,
        "period_start": pd.Timestamp("2022-01-31"),
        "period_end": pd.Timestamp("2023-01-29"),
        "filed": pd.Timestamp("2023-03-15"),
    }
    fy2023 = {
        "concept": "revenue",
        "value": 152,
        "fiscal_year": 2023,
        "period_start": pd.Timestamp("2023-01-30"),
        "period_end": pd.Timestamp("2024-01-28"),
        "filed": pd.Timestamp("2024-03-13"),
    }
    # fiscal 2022 again, as the prior year column of the fiscal 2023 10-K
    comparative = {**fy2022, "fiscal_year": 2023, "filed": fy2023["filed"]}

    out = label_fiscal_periods(make_facts(fy2022, fy2023, comparative))

    by_end = out.groupby("period_end")["fiscal_year"].unique()
    assert list(by_end[pd.Timestamp("2023-01-29")]) == [2022]
    assert list(by_end[pd.Timestamp("2024-01-28")]) == [2023]


def test_label_drops_the_prior_year_end_balance_sheet_inside_a_10q():
    q2 = {**QUARTER, "concept": "revenue", "value": 30}
    prior_year_end = {
        **QUARTER,
        "concept": "assets",
        "value": 500,
        "period_start": pd.NaT,
        "period_end": pd.Timestamp("2019-02-03"),
    }

    out = label_fiscal_periods(make_facts(q2, prior_year_end))

    assert list(out["concept"]) == ["revenue"]


def test_build_table_keeps_a_year_end_balance_the_next_10q_reports_again():
    year_end = {"concept": "assets", "value": 500, "period_start": pd.NaT}
    # Q1 10-Q filed later: its own quarter end, plus the year end as comparative
    q1 = {
        "concept": "assets",
        "value": 520,
        "form": "10-Q",
        "fiscal_year": 2021,
        "fiscal_period": "Q1",
        "period_start": pd.NaT,
        "period_end": pd.Timestamp("2020-05-03"),
        "filed": pd.Timestamp("2020-06-01"),
    }
    year_end_again = {**q1, "value": 500, "period_end": pd.Timestamp("2020-02-02")}

    out = build_table(make_facts(year_end, q1, year_end_again), ANNUAL_FORMS, ANNUAL_DAYS)

    assert list(out["form"]) == ["10-K"]
    assert list(out["value"]) == [500]
    assert list(out["fiscal_year"]) == [2020]


def annual_revenue(year_end: str, fiscal_year: int, value: float, filed: str) -> dict:
    end = pd.Timestamp(year_end)
    return {
        "concept": "revenue",
        "value": value,
        "fiscal_year": fiscal_year,
        "period_start": end - pd.Timedelta(days=364),
        "period_end": end,
        "filed": pd.Timestamp(filed),
    }


def test_label_outvotes_a_filing_that_tagged_the_wrong_fiscal_year():
    # CRM calls the year ending Jan 2021 fiscal 2021, but that 10-K says 2020
    df = make_facts(
        annual_revenue("2020-01-31", 2020, 17, "2020-03-05"),
        annual_revenue("2021-01-31", 2020, 21, "2021-03-17"),
        annual_revenue("2022-01-31", 2022, 26, "2022-03-11"),
    )

    out = label_fiscal_periods(df)

    assert list(out.sort_values("period_end")["fiscal_year"]) == [2020, 2021, 2022]


def test_build_table_labels_a_10k_tagged_q4_as_fiscal_year():
    df = make_facts({"concept": "revenue", "value": 100, "fiscal_period": "Q4"})

    out = build_table(df, ANNUAL_FORMS, ANNUAL_DAYS)

    assert list(out["fiscal_period"]) == ["FY"]


def test_build_table_collapses_a_quarter_tagged_with_two_start_dates():
    original = {**QUARTER, "concept": "revenue", "value": 30}
    # next year's comparative starts the same quarter one day later
    comparative = {
        **original,
        "period_start": pd.Timestamp("2019-05-07"),
        "fiscal_year": 2021,
        "filed": pd.Timestamp("2020-09-01"),
    }
    next_q2 = {
        **original,
        "value": 33,
        "fiscal_year": 2021,
        "period_start": pd.Timestamp("2020-05-04"),
        "period_end": pd.Timestamp("2020-08-02"),
        "filed": pd.Timestamp("2020-09-01"),
    }

    out = build_table(make_facts(original, comparative, next_q2), QUARTERLY_FORMS, QUARTER_DAYS)

    assert list(out["fiscal_year"]) == [2020, 2021]
    assert list(out["value"]) == [30, 33]


def test_filter_form_drops_a_period_that_ends_after_its_filing():
    # WMT's fiscal 2012 10-K tagged cash at 2012-12-31, a typo for 2012-01-31
    typo = {
        "concept": "cash",
        "value": 6,
        "period_start": pd.NaT,
        "period_end": pd.Timestamp("2020-12-31"),
    }

    out = filter_form(make_facts({"concept": "revenue", "value": 100}, typo), ANNUAL_FORMS, ANNUAL_DAYS)

    assert list(out["concept"]) == ["revenue"]
