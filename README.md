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

The SEC client, the parser and the DuPont core of the ratio engine are built and
tested. The rest is scaffolding, so the analyzer does not yet run end to end and
the dashboard does not yet render anything.

Working today:

- `src/edgar_client.py`, a cached and rate limited client for the EDGAR REST
  APIs, the ticker to CIK lookup, and `company_facts()`, the per filer pull.
  All 10 tickers in `config/companies.yml` have been fetched and cached, from
  Costco's 460 us-gaap concepts up to Salesforce's 691.
- `config/companies.yml`, the two peer sets the analysis will run over.
- `load_all_facts()` in `src/parse.py`, which flattens all 10 cached filings
  into one long table of 261,095 us-gaap facts: ticker, concept, unit, fiscal
  year and period, form, period start and end, filed date, and value. Period
  start matters because a 10-Q reports both the quarter and the year to date
  under the same period end.
- `resolve_concepts()` and `drop_restatements()` in `src/parse.py`. The first
  maps raw tags onto the 14 internal metrics, taking the highest priority tag
  available for each period, so a filer that changed tags mid history still gets
  one unbroken series. The second keeps the latest filed value of each fact. Run
  over the 10 cached filers they cut the table to 10,683 facts with no
  duplicates left, and give the same result in either order.
- `net_margin()`, `asset_turnover()`, `equity_multiplier()`,
  `return_on_equity()` and `dupont()` in `src/ratios.py`. `dupont()` splits ROE
  into its three drivers, and the tests check that their product matches ROE
  computed directly, including for a loss making company and one with negative
  equity. On the latest year of all 10 cached filers the two agree to floating
  point.
- 55 tests passing.

Not built yet:

- Form filtering (10-K for annual, 10-Q for quarterly) and writing the
  processed table to disk.
- The rest of `src/ratios.py`: gross and operating margin, ROA, liquidity,
  leverage, cash flow and growth ratios, and peer percentile rank.
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
priority list per metric, period by period, rather than trusting one tag.

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

Pull everything a filer has ever reported. That runs 3 to 5 MB per company, so
let it land in the cache once and work off disk after that:

```python
from src.edgar_client import company_facts, make_session, ticker_to_cik

with make_session() as session:
    facts = company_facts(ticker_to_cik(session)["MSFT"], session)
    print(facts["entityName"], len(facts["facts"]["us-gaap"]), "us-gaap concepts")
```

`USER_AGENT` in `src/edgar_client.py` carries my name and email, per the
[SEC fair access policy](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
Replace it with your own if you reuse this. Keep calls sequential, since this
client does not coordinate rate limits across processes or threads.

## What is left

In rough order:

1. Filter the resolved table by form and write it to `data/processed/`.
2. Finish the ratio engine. The DuPont breakdown of ROE into net margin, asset
   turnover and the equity multiplier is done, which is the part that answers
   why one company's return beats another's. Margins, ROA, liquidity, leverage,
   cash flow, growth and peer rank are not.
3. Add the narration layer and its number verification.
4. Put a Streamlit dashboard on top and deploy it.

## License

MIT.
