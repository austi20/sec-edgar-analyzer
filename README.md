# SEC EDGAR Financial Statement Analyzer

[![tests](https://github.com/austi20/sec-edgar-analyzer/actions/workflows/tests.yml/badge.svg)](https://github.com/austi20/sec-edgar-analyzer/actions/workflows/tests.yml)

Public companies file their financials with the SEC in XBRL, so in theory
comparing two of them is easy. In practice they tag the same line item three
different ways, restate it a year later, and bury it in a JSON blob holding a
decade of everything else they ever reported. This project pulls those filings,
normalizes the tags into one clean table, computes the ratios an analyst
actually uses, and has a local LLM narrate the result without letting it invent
a single number.

## Where this is now

The SEC client is built and tested. Everything downstream of it is scaffolding,
so the analyzer does not yet run end to end and the dashboard does not yet
render anything.

Working today:

- `src/edgar_client.py`, a cached and rate limited client for the EDGAR REST
  APIs, plus the ticker to CIK lookup.
- `config/companies.yml`, the two peer sets the analysis will run over.
- 27 tests passing, 3 skipped because they cover modules that are still stubs.

Not built yet:

- `company_facts()`, the per filer financial pull.
- `src/parse.py`, which flattens the filings and handles tag aliasing and
  restatements.
- `src/ratios.py`, every ratio and the DuPont decomposition.
- `src/narrate.py`, the LLM layer.
- `app/streamlit_app.py`, the dashboard.

I would rather say that plainly than have you clone it and find
`NotImplementedError`.

## The problems this has to solve

These are the parts worth talking about, and they are why the project is more
than a loop over an API.

**The SEC will block you.** Requests need a descriptive User Agent carrying a
real contact email. The client waits at least 0.15 seconds between calls,
retries 429 and 503 up to three times with exponential backoff, and honors
`Retry-After` when the response sends one.

**CIKs need zero padding to 10 digits** in URLs, so Apple is 320193 in one place
and `CIK0000320193` in another. Getting this wrong costs an afternoon.

**The same number has several names.** Revenue shows up as
`RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, or
`SalesRevenueNet` depending on the filer and the year. The parser resolves a
priority list per metric rather than trusting one tag.

**Companies restate.** The same period end appears more than once with different
values, so the rule is to keep whichever version was filed most recently.

**Ratios only mean something against peers.** The two peer sets are each
internally comparable on purpose. Banks and insurers are deliberately excluded,
because their statements use different `us-gaap` concepts and would quietly
break the ratio engine rather than error out.

**The LLM is not allowed to do arithmetic.** It receives a table of numbers the
deterministic pipeline already computed and narrates those. Every figure in its
output gets checked against that table before the summary is cached, and the
deployed app reads cached summaries, so it never needs Ollama or a GPU at
request time.

## Caching

Every successful response is written atomically to `data/raw/`, keyed by a
SHA256 of the full URL. A cache hit makes no HTTP request at all. Entries never
expire, so delete the file to refresh it. Writes go through a temp file and get
renamed into place, which means an interrupted write cannot leave behind a
corrupt file that later reads as a valid cache hit.

## Running it

Use Python 3.12, which is what the pinned dependencies target.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Fetch one SEC resource, where the second call comes from the cache:

```python
from src.edgar_client import fetch_json, make_session

with make_session() as session:
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    filing = fetch_json(url, session)
    cached = fetch_json(url, session)
    assert filing == cached
    print(filing["name"])
```

Resolve tickers to padded CIKs, through the same cache:

```python
from src.edgar_client import ticker_to_cik

lookup = ticker_to_cik()
print(lookup["MSFT"])  # "0000789019"
```

`USER_AGENT` in `src/edgar_client.py` carries my name and email, per the
[SEC fair access policy](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
Replace it with your own if you reuse this. Keep calls sequential, since this
client does not coordinate rate limits across processes or threads.

## What is left

In rough order:

1. Finish `company_facts()` so a ticker returns its full XBRL history.
2. Flatten those filings into one tidy long table, resolving tag aliases and
   dropping restated duplicates.
3. Build the ratio engine, including the DuPont breakdown of ROE into net
   margin, asset turnover and the equity multiplier, which is the part that
   answers why one company's return beats another's.
4. Add the narration layer and its number verification.
5. Put a Streamlit dashboard on top and deploy it.

## License

MIT.
