"""Flatten companyfacts JSON into one tidy long DataFrame.

Columns: ticker, concept, unit, fiscal_year, fiscal_period, form,
         period_start, period_end, filed, value

The three things that always bite:
  - concept aliasing  : resolve a priority list per metric (see CONCEPT_PRIORITY)
  - restatements      : keep the most recently `filed` value for a given period_end
  - form filtering    : 10-K for annual, 10-Q for quarterly
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from src.edgar_client import company_facts, make_session, ticker_to_cik

COMPANIES_PATH = Path(__file__).resolve().parents[1] / "config" / "companies.yml"
PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"

ANNUAL_FORMS = ["10-K", "10-K/A"]
QUARTERLY_FORMS = ["10-Q", "10-Q/A"]
# end minus start, in days. 52 and 53 week years run 363 or 370
ANNUAL_DAYS = (350, 380)
# 13 or 14 week quarters, or calendar quarters
QUARTER_DAYS = (80, 100)

COLUMNS = [
    "ticker",
    "concept",
    "unit",
    "fiscal_year",
    "fiscal_period",
    "form",
    "period_start",
    "period_end",
    "filed",
    "value",
]

CONCEPT_PRIORITY: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "assets": ["Assets"],
    "assets_current": ["AssetsCurrent"],
    "liabilities": ["Liabilities"],
    "liabilities_current": ["LiabilitiesCurrent"],
    "equity": ["StockholdersEquity"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "inventory": ["InventoryNet"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "interest_expense": ["InterestExpense"],
}

# Apart from the concept, what makes one fact distinct. period_start is part of it
# because a 10-Q reports the quarter and the year to date under one period_end;
# instants (Assets) have no start, so it is NaT for them.
_PERIOD_KEY = ["ticker", "unit", "period_start", "period_end"]


def flatten_company_facts(facts: dict, ticker: str) -> pd.DataFrame:
    """One row per reported us-gaap fact."""
    rows = []
    for concept, detail in facts["facts"].get("us-gaap", {}).items():
        for unit, entries in detail["units"].items():
            for entry in entries:
                rows.append(
                    {
                        "ticker": ticker,
                        "concept": concept,
                        "unit": unit,
                        "fiscal_year": entry.get("fy"),
                        "fiscal_period": entry.get("fp"),
                        "form": entry["form"],
                        # instants like Assets have no start
                        "period_start": entry.get("start"),
                        "period_end": entry["end"],
                        "filed": entry["filed"],
                        "value": entry["val"],
                    }
                )

    df = pd.DataFrame(rows, columns=COLUMNS)
    # 8-K facts carry no fiscal year
    df["fiscal_year"] = df["fiscal_year"].astype("Int64")
    for column in ["period_start", "period_end", "filed"]:
        df[column] = pd.to_datetime(df[column])
    return df


def load_all_facts(companies_path: Path = COMPANIES_PATH) -> pd.DataFrame:
    """Flatten every filer in companies.yml into one long table."""
    with companies_path.open(encoding="utf-8") as f:
        peer_sets = yaml.safe_load(f)["peer_sets"]

    frames = []
    with make_session() as session:
        ciks = ticker_to_cik(session)
        for tickers in peer_sets.values():
            for ticker in tickers:
                facts = company_facts(ciks[ticker], session)
                frames.append(flatten_company_facts(facts, ticker))
    return pd.concat(frames, ignore_index=True)


def resolve_concepts(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse raw us-gaap concepts onto the internal schema via CONCEPT_PRIORITY.

    Priority is applied per period, not per filer, so a filer that switched tags
    part way through its history still gets one unbroken series. Concepts outside
    the schema are dropped. Restated duplicates of the winning tag are kept;
    drop_restatements() collapses them, in either order.
    """
    metric = {raw: name for name, raws in CONCEPT_PRIORITY.items() for raw in raws}
    rank = {raw: i for raws in CONCEPT_PRIORITY.values() for i, raw in enumerate(raws)}

    out = df[df["concept"].isin(metric)].copy()
    out["rank"] = out["concept"].map(rank)
    out["concept"] = out["concept"].map(metric)
    # dropna=False: instants have no period_start and groupby would drop them
    best = out.groupby(["concept", *_PERIOD_KEY], dropna=False)["rank"].transform("min")
    return out[out["rank"] == best].drop(columns="rank").reset_index(drop=True)


def drop_restatements(df: pd.DataFrame, key: list[str] | None = None) -> pd.DataFrame:
    """Keep the most recently filed value of each fact.

    By default a fact is one (ticker, concept, unit, period_start, period_end).
    Uses drop_duplicates rather than groupby because it treats NaT period_starts
    as equal, where groupby would silently drop every instant.
    """
    if key is None:
        key = ["concept", *_PERIOD_KEY]
    return (
        df.sort_values("filed", kind="stable")
        .drop_duplicates(subset=key, keep="last")
        .reset_index(drop=True)
    )


def filter_form(df: pd.DataFrame, forms: list[str], days: tuple[int, int]) -> pd.DataFrame:
    """Keep facts from the given forms whose duration matches the table.

    A 10-K also tags some quarters and a 10-Q also tags year to date, so the
    form alone is not enough. Instants have no duration and always pass.
    A period ending after its own filing date is a filer typo and is dropped.
    """
    length = (df["period_end"] - df["period_start"]).dt.days
    right_length = df["period_start"].isna() | length.between(*days)
    already_ended = df["period_end"] <= df["filed"]
    return df[df["form"].isin(forms) & right_length & already_ended].reset_index(drop=True)


def label_fiscal_periods(df: pd.DataFrame) -> pd.DataFrame:
    """Relabel each fact with the fiscal year and period it actually covers.

    fy and fp in companyfacts describe the filing, not the fact, so a prior year
    shown as a comparative carries the newer filing's year. Only a filing's own
    period, its latest period_end, is labeled by it. Facts whose period_end was
    never a filing's own period are dropped, like the prior year end balance
    sheet inside a 10-Q.

    Even own periods are sometimes mislabeled by the filer, so the year comes
    from the filer's usual gap between fiscal year and calendar year of the
    period end, per fiscal period, rather than from any single filing.
    """
    # no accession number kept, so ticker, form and filed date stand in for it
    latest_end = df.groupby(["ticker", "form", "filed"])["period_end"].transform("max")
    own = df[df["period_end"] == latest_end].drop_duplicates(subset=["ticker", "form", "filed"])
    own = own.assign(offset=own["fiscal_year"] - own["period_end"].dt.year)

    # most common offset outvotes the odd mislabeled filing
    offsets = own.groupby(["ticker", "fiscal_period"])["offset"].agg(lambda s: s.mode().iloc[0])
    periods = drop_restatements(own, key=["ticker", "period_end"])

    out = df.drop(columns=["fiscal_year", "fiscal_period"])
    out = out.merge(periods[["ticker", "period_end", "fiscal_period"]], on=["ticker", "period_end"])
    out = out.merge(offsets.reset_index(), on=["ticker", "fiscal_period"])
    out["fiscal_year"] = (out["period_end"].dt.year + out["offset"]).astype("Int64")
    return out[COLUMNS]


def build_table(df: pd.DataFrame, forms: list[str], days: tuple[int, int]) -> pd.DataFrame:
    """Resolved facts to one labeled annual or quarterly table, one value per period.

    Filters before dropping restatements. A year end balance is reported again
    in the next 10-Qs, and deduplicating first would keep the 10-Q copy and lose
    it from the annual table. Deduplicates on the label, not the exact dates,
    because a comparative sometimes tags the same quarter a day or a week apart.
    """
    table = filter_form(df, forms, days)
    if forms == ANNUAL_FORMS:
        # a few 10-Ks are tagged Q4
        table = table.assign(fiscal_period="FY")
    table = label_fiscal_periods(table)
    table = drop_restatements(table, key=["ticker", "concept", "unit", "fiscal_year", "fiscal_period"])
    return table.sort_values(["ticker", "concept", "period_end"]).reset_index(drop=True)


def write_processed(out_dir: Path = PROCESSED_DIR) -> None:
    """Write annual.parquet and quarterly.parquet from the cached filings."""
    resolved = resolve_concepts(load_all_facts())
    out_dir.mkdir(parents=True, exist_ok=True)

    annual = build_table(resolved, ANNUAL_FORMS, ANNUAL_DAYS)
    quarterly = build_table(resolved, QUARTERLY_FORMS, QUARTER_DAYS)
    annual.to_parquet(out_dir / "annual.parquet", index=False)
    quarterly.to_parquet(out_dir / "quarterly.parquet", index=False)
    print(f"annual: {len(annual)} facts, quarterly: {len(quarterly)} facts")


if __name__ == "__main__":
    write_processed()
