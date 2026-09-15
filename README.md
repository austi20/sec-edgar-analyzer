# SEC EDGAR Financial Statement Analyzer (AI-assisted)

Pulls 10-K/10-Q XBRL filings for two peer sets of five public companies from the SEC EDGAR API,
normalizes inconsistently tagged `us-gaap` concepts into a tidy dataset, computes standard
financial ratios (margins, liquidity, leverage, DuPont ROE), and narrates the results with a
local LLM that is constrained to numbers the pipeline actually computed. Ships as a deployed
Streamlit dashboard.

**Due:** Sunday, October 11, 2026 &nbsp;|&nbsp; **Estimated effort:** ~22 hours &nbsp;|&nbsp; **Type:** portfolio project

## Current implementation (September 15, 2026)

Milestone 1, steps 1-4: repository setup, cached HTTP client, ticker -> CIK
lookup, and the two peer sets in `config/companies.yml`. `company_facts` (the
per-filer financial pull) and the parser/ratio/narrate modules are starter
scaffolding for later milestones. The analyzer and dashboard are not yet
runnable end to end.

Use Python 3.12 for the pinned project dependencies. From PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Fetch one SEC JSON resource (the second call uses the disk cache):

```python
from src.edgar_client import fetch_json, make_session

with make_session() as session:
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    filing = fetch_json(url, session)
    cached = fetch_json(url, session)
    assert filing == cached
    print(filing["name"])
```

Resolve tickers to zero-padded CIKs (also cached, same client):

```python
from src.edgar_client import ticker_to_cik

lookup = ticker_to_cik()
print(lookup["MSFT"])  # "0000789019"
```

The client identifies requests with the contact in `USER_AGENT`; replace it with
your own name and email when reusing this project. It waits at least 0.15 seconds
before every request and retries HTTP 429/503 up to three times with exponential
backoff, honoring `Retry-After`. Requests have a 30-second timeout. Use sequential
calls; this small client does not coordinate rate limits across processes or threads.
See the [SEC fair access policy](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

Successful JSON responses are written atomically to `data/raw/<SHA256-of-URL>.json`.
Cache hits make no HTTP request. Cache entries do not expire; remove the matching
file to refresh it. HTTP, timeout, invalid JSON, corrupt cache, and filesystem
errors propagate to the caller. Caller-owned sessions remain open.

The skipped parser and ratio tests belong to later milestones. `tasks.bat data`
is reserved for those milestones; use the Python example above for today's client.

---

## Implementation plan

| Milestone | Focus | Target week | Est. hours | Status |
|---|---|---|---|---|
| 1 | Repo setup, cached client, ticker -> CIK lookup, peer sets | Sept 14 | ~4 | Steps 1-4 done; `company_facts` pull pending |
| 2 | Normalize XBRL filings into a tidy table | Sept 21 | ~5 | Not started |
| 3 | Ratio engine + DuPont ROE decomposition | Sept 28 | ~4 | Not started |
| 4 | Local LLM narrative layer (Ollama, number-verified) | Oct 5 | ~6 | Not started |
| 5 | Streamlit dashboard, deploy, write-up | Oct 11 | ~3 | Not started |

Detailed per-milestone tasks, resource links, and scheduling notes are kept in a local
`PLAN.md` (not tracked in this repo).
