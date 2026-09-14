"""Flatten companyfacts JSON into one tidy long DataFrame.

Columns: ticker, concept, unit, fiscal_year, fiscal_period, period_end,
         value, form, filed, accession

The three things that always bite:
  - concept aliasing  : resolve a priority list per metric (see CONCEPT_PRIORITY)
  - restatements      : keep the most recently `filed` value for a given period_end
  - form filtering    : 10-K for annual, 10-Q for quarterly
"""

from __future__ import annotations

import pandas as pd

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


def flatten_company_facts(facts: dict, ticker: str) -> pd.DataFrame:
    """One row per reported fact."""
    raise NotImplementedError


def resolve_concepts(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse raw us-gaap concepts onto the internal schema via CONCEPT_PRIORITY."""
    raise NotImplementedError


def drop_restatements(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the most recently filed value per (ticker, concept, period_end)."""
    raise NotImplementedError
