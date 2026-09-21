"""Polite, cached client for the SEC EDGAR XBRL REST APIs.

Two things that will cost hours if missed:
  1. CIKs must be zero-padded to 10 digits in URLs (Apple 320193 -> CIK0000320193).
  2. SEC requires a descriptive User-Agent with a contact email or requests get blocked.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests

USER_AGENT = "Gunnar Austin gunnar.austin@gmail.com"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

REQUEST_DELAY_SECONDS = 0.15
RETRY_STATUSES = (429, 503)
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_json(url: str, session: requests.Session | None = None) -> dict:
    """Fetch sequentially, retry 429/503, and persist valid JSON by full URL.

    Cache entries never expire. Remove an entry to refresh it. Errors propagate;
    only sessions created here are closed here.
    """
    cache_path = RAW_DIR / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json")
    if cache_path.exists():
        with cache_path.open(encoding="utf-8") as cached:
            return json.load(cached)

    active_session = make_session() if session is None else session
    delay = REQUEST_DELAY_SECONDS
    try:
        for attempt in range(MAX_RETRIES + 1):
            time.sleep(delay)
            response = active_session.get(
                url, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}
            )
            try:
                if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                    delay = max(REQUEST_DELAY_SECONDS, float(2**attempt))
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        delay = max(delay, _retry_after_seconds(retry_after))
                    continue
                response.raise_for_status()
                payload = response.json()
            finally:
                response.close()

            RAW_DIR.mkdir(parents=True, exist_ok=True)
            temporary_path = None
            try:
                # Replace only complete JSON files so interrupted writes cannot poison a hit.
                with NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=RAW_DIR, suffix=".tmp", delete=False
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    json.dump(payload, temporary, ensure_ascii=False)
                temporary_path.replace(cache_path)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            return payload
    finally:
        if session is None:
            active_session.close()
    raise RuntimeError("Retry loop exited without a response")


def _retry_after_seconds(value: str) -> float:
    """Interpret HTTP delay-seconds or an HTTP date; malformed values use backoff."""
    if value.strip().isdigit():
        return float(value)
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return 0.0


def pad_cik(cik: int | str) -> str:
    """Zero-pad a CIK to 10 digits."""
    return str(int(cik)).zfill(10)


def ticker_to_cik(session: requests.Session | None = None) -> dict[str, str]:
    """Map ticker -> zero-padded CIK from company_tickers.json."""
    payload = fetch_json(TICKERS_URL, session)
    return {entry["ticker"]: pad_cik(entry["cik_str"]) for entry in payload.values()}


def company_facts(cik: int | str, session: requests.Session | None = None) -> dict:
    """Every XBRL fact a filer has reported, keyed by its zero-padded CIK."""
    return fetch_json(COMPANY_FACTS_URL.format(cik=pad_cik(cik)), session)
