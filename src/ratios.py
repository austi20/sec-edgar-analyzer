"""One pure function per ratio. Every one of these is unit-tested."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from src.parse import COMPANIES_PATH, CONCEPT_PRIORITY, PROCESSED_DIR

# a percentile among two companies says nothing
MIN_PEERS = 3
# a fiscal year ending in Jan to Mar belongs to the calendar year before
YEAR_END_SHIFT = pd.DateOffset(months=3)

RATIO_COLUMNS = [
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roa",
    "roe",
    "current_ratio",
    "quick_ratio",
    "debt_to_equity",
    "interest_coverage",
    "equity_multiplier",
    "asset_turnover",
    "fcf_margin",
    "revenue_growth",
    "net_income_growth",
]

# --- Profitability ---------------------------------------------------------


def gross_margin(gross_profit: float, revenue: float) -> float:
    return gross_profit / revenue


def operating_margin(operating_income: float, revenue: float) -> float:
    return operating_income / revenue


def net_margin(net_income: float, revenue: float) -> float:
    return net_income / revenue


def return_on_assets(net_income: float, assets: float) -> float:
    return net_income / assets


def return_on_equity(net_income: float, equity: float) -> float:
    return net_income / equity


# --- Liquidity -------------------------------------------------------------


def current_ratio(assets_current: float, liabilities_current: float) -> float:
    return assets_current / liabilities_current


def quick_ratio(assets_current: float, inventory: float, liabilities_current: float) -> float:
    return (assets_current - inventory) / liabilities_current


# --- Leverage --------------------------------------------------------------


def debt_to_equity(liabilities: float, equity: float) -> float:
    return liabilities / equity


def interest_coverage(operating_income: float, interest_expense: float) -> float:
    return operating_income / interest_expense


def equity_multiplier(assets: float, equity: float) -> float:
    return assets / equity


# --- Efficiency ------------------------------------------------------------


def asset_turnover(revenue: float, assets: float) -> float:
    return revenue / assets


# --- Cash ------------------------------------------------------------------


def free_cash_flow(cfo: float, capex: float) -> float:
    return cfo - capex


def fcf_margin(cfo: float, capex: float, revenue: float) -> float:
    return free_cash_flow(cfo, capex) / revenue


# --- Growth ----------------------------------------------------------------


def yoy_growth(current: float, prior: float) -> float:
    # abs keeps the sign right when prior is a loss
    return (current - prior) / abs(prior)


# --- DuPont ----------------------------------------------------------------


def dupont(net_income: float, revenue: float, assets: float, equity: float) -> dict[str, float]:
    """ROE = net margin x asset turnover x equity multiplier.

    The most interview-useful function in the repo: it answers *why* one
    company's return beats another's.

    `roe` is the product of the three drivers, so it equals return_on_equity()
    up to floating point.
    """
    margin = net_margin(net_income, revenue)
    turnover = asset_turnover(revenue, assets)
    leverage = equity_multiplier(assets, equity)
    return {
        "net_margin": margin,
        "asset_turnover": turnover,
        "equity_multiplier": leverage,
        "roe": margin * turnover * leverage,
    }


def build_ratios(annual: pd.DataFrame) -> pd.DataFrame:
    """One row per ticker and fiscal year, one column per ratio.

    `fiscal_year` is each filer's own label and does not line up across filers
    (Home Depot's year ending Feb 2026 is its fiscal 2025, Walmart's is fiscal
    2026). `period_year` is the common year used for peer comparison.

    A missing input leaves the ratio blank. Negative equity blanks the equity
    ratios, since ROE on negative equity ranks a profitable company last.
    """
    facts = annual.pivot(index=["ticker", "fiscal_year"], columns="concept", values="value")
    # a concept no filer reported still gets a blank column
    facts = facts.reindex(columns=list(CONCEPT_PRIORITY)).reset_index()
    out = facts[["ticker", "fiscal_year"]].copy()
    period_end = annual.groupby(["ticker", "fiscal_year"])["period_end"].max()
    period_end = period_end.reindex(pd.MultiIndex.from_frame(out)).to_numpy()
    out["period_year"] = (pd.Series(period_end) - YEAR_END_SHIFT).dt.year

    out["gross_margin"] = gross_margin(facts["gross_profit"], facts["revenue"])
    out["operating_margin"] = operating_margin(facts["operating_income"], facts["revenue"])
    out["net_margin"] = net_margin(facts["net_income"], facts["revenue"])
    out["roa"] = return_on_assets(facts["net_income"], facts["assets"])
    out["current_ratio"] = current_ratio(facts["assets_current"], facts["liabilities_current"])
    out["quick_ratio"] = quick_ratio(
        facts["assets_current"], facts["inventory"], facts["liabilities_current"]
    )
    out["interest_coverage"] = interest_coverage(
        facts["operating_income"], facts["interest_expense"]
    )
    out["asset_turnover"] = asset_turnover(facts["revenue"], facts["assets"])
    out["fcf_margin"] = fcf_margin(facts["cfo"], facts["capex"], facts["revenue"])

    positive_equity = facts["equity"].where(facts["equity"] > 0)
    out["roe"] = return_on_equity(facts["net_income"], positive_equity)
    out["debt_to_equity"] = debt_to_equity(facts["liabilities"], positive_equity)
    out["equity_multiplier"] = equity_multiplier(facts["assets"], positive_equity)

    # growth needs last year's row, matched on fiscal_year so a gap gives blank
    prior = facts[["ticker", "fiscal_year", "revenue", "net_income"]].copy()
    prior["fiscal_year"] = prior["fiscal_year"] + 1
    prior = prior.rename(columns={"revenue": "revenue_prior", "net_income": "net_income_prior"})
    both = facts[["ticker", "fiscal_year", "revenue", "net_income"]].merge(
        prior, on=["ticker", "fiscal_year"], how="left"
    )
    out["revenue_growth"] = yoy_growth(both["revenue"], both["revenue_prior"])
    out["net_income_growth"] = yoy_growth(both["net_income"], both["net_income_prior"])

    return out[["ticker", "fiscal_year", "period_year", *RATIO_COLUMNS]]


def peer_percentile_rank(ratios: pd.DataFrame, peer_sets: dict[str, list[str]]) -> pd.DataFrame:
    """Percentile of each ratio among the company's peers in the same period year.

    The highest value in a group scores 1.0 and the lowest scores 1 / n. This
    is position, not quality: a low debt to equity ranks low. Fewer than
    MIN_PEERS values in a group leaves the rank blank.
    """
    peer_set_of = {}
    for name, tickers in peer_sets.items():
        for ticker in tickers:
            peer_set_of[ticker] = name

    ranked = ratios.copy()
    ranked.insert(0, "peer_set", ranked["ticker"].map(peer_set_of))
    ranked = ranked.dropna(subset=["peer_set"])

    columns = [c for c in RATIO_COLUMNS if c in ranked.columns]
    grouped = ranked.groupby(["peer_set", "period_year"])[columns]
    percentiles = grouped.rank(pct=True)
    enough = grouped.transform("count") >= MIN_PEERS
    ranked[columns] = percentiles.where(enough)
    return ranked.reset_index(drop=True)


def write_ratios(out_dir: Path = PROCESSED_DIR, companies_path: Path = COMPANIES_PATH) -> None:
    """Write ratios.parquet and peer_rank.parquet from annual.parquet."""
    with companies_path.open(encoding="utf-8") as f:
        peer_sets = yaml.safe_load(f)["peer_sets"]

    annual = pd.read_parquet(out_dir / "annual.parquet")
    ratios = build_ratios(annual)
    peer_rank = peer_percentile_rank(ratios, peer_sets)
    ratios.to_parquet(out_dir / "ratios.parquet", index=False)
    peer_rank.to_parquet(out_dir / "peer_rank.parquet", index=False)
    print(f"ratios: {len(ratios)} rows, peer_rank: {len(peer_rank)} rows")


if __name__ == "__main__":
    write_ratios()
