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


def drop_restatements(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the most recently filed value of each fact.

    A fact is one (ticker, concept, unit, period_start, period_end). Uses
    drop_duplicates rather than groupby because it treats NaT period_starts as
    equal, where groupby would silently drop every instant.
    """
    return (
        df.sort_values("filed", kind="stable")
        .drop_duplicates(subset=["concept", *_PERIOD_KEY], keep="last")
        .reset_index(drop=True)
    )
