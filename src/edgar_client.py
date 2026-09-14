"""Polite, cached client for the SEC EDGAR XBRL REST APIs.

Two things that will cost hours if missed:
  1. CIKs must be zero-padded to 10 digits in URLs (Apple 320193 -> CIK0000320193).
  2. SEC requires a descriptive User-Agent with a contact email or requests get blocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

USER_AGENT = "Gunnar Austin gunnar.austin@gmail.com"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

REQUEST_DELAY_SECONDS = 0.15
RETRY_STATUSES = (429, 503)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_json(url: str, session: requests.Session | None = None) -> dict:
    """GET with polite delay and retry on 429/503, cached to data/raw/ by URL."""
    raise NotImplementedError


def pad_cik(cik: int | str) -> str:
    """Zero-pad a CIK to 10 digits."""
    return str(int(cik)).zfill(10)


def ticker_to_cik(session: requests.Session | None = None) -> dict[str, str]:
    """Map ticker -> zero-padded CIK from company_tickers.json."""
    raise NotImplementedError


def company_facts(ticker: str, session: requests.Session | None = None) -> dict:
    raise NotImplementedError
