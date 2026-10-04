"""One pure function per ratio. Every one of these is unit-tested."""

from __future__ import annotations

# --- Profitability ---------------------------------------------------------


def gross_margin(gross_profit: float, revenue: float) -> float:
    raise NotImplementedError


def operating_margin(operating_income: float, revenue: float) -> float:
    raise NotImplementedError


def net_margin(net_income: float, revenue: float) -> float:
    return net_income / revenue


def return_on_assets(net_income: float, assets: float) -> float:
    raise NotImplementedError


def return_on_equity(net_income: float, equity: float) -> float:
    return net_income / equity


# --- Liquidity -------------------------------------------------------------


def current_ratio(assets_current: float, liabilities_current: float) -> float:
    raise NotImplementedError


def quick_ratio(assets_current: float, inventory: float, liabilities_current: float) -> float:
    raise NotImplementedError


# --- Leverage --------------------------------------------------------------


def debt_to_equity(liabilities: float, equity: float) -> float:
    raise NotImplementedError


def interest_coverage(operating_income: float, interest_expense: float) -> float:
    raise NotImplementedError


def equity_multiplier(assets: float, equity: float) -> float:
    return assets / equity


# --- Efficiency ------------------------------------------------------------


def asset_turnover(revenue: float, assets: float) -> float:
    return revenue / assets


# --- Cash ------------------------------------------------------------------


def free_cash_flow(cfo: float, capex: float) -> float:
    raise NotImplementedError


def fcf_margin(cfo: float, capex: float, revenue: float) -> float:
    raise NotImplementedError


# --- Growth ----------------------------------------------------------------


def yoy_growth(current: float, prior: float) -> float:
    raise NotImplementedError


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


def peer_percentile_rank(values, within: str = "peer_set"):
    """Percentile rank of each ratio within its peer set."""
    raise NotImplementedError
