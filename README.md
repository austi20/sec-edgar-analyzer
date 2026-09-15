# SEC EDGAR Financial Statement Analyzer (AI-assisted)

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

**Due: Sunday, October 11, 2026** | **Estimated effort: ~22 hours** | **Type: portfolio project**

---

## Background: why this project

The target roles are data analytics internships and entry-level analyst jobs, preferring financial
services and AI. Most student portfolios in this space are Kaggle notebooks on clean, pre-packaged
datasets. Hiring managers in financial services discount those, because the work they actually need
done is: pull messy filings from a regulated source, normalize them, compute the metrics an analyst
would actually quote, and present it so a non-technical person can act on it.

This project does exactly that end to end, and it closes four gaps at once:

| Gap | How this closes it |
|---|---|
| **Finance domain credibility** | Works directly with 10-K / 10-Q XBRL data and standard ratio analysis, the vocabulary of the job |
| **API / data engineering** | Paginated public API, rate limits, caching, schema normalization, restatement handling |
| **GenAI that is not a toy** | A local LLM writes the narrative, constrained to numbers the pipeline computed |
| **A deployed, clickable artifact** | A live Streamlit URL a recruiter can open in 10 seconds, not a notebook they must run |

The "AI-assisted" framing matters: the LLM never invents a number. It narrates values the
deterministic pipeline already produced. That distinction is worth saying out loud in an interview,
because it is the difference between a demo and something a regulated employer could actually use.

---

## Skills and tools covered

- **Python**: `requests`, `pandas`, `pathlib`, `logging`, type hints
- **APIs**: SEC EDGAR XBRL REST APIs (no key required, User-Agent header required)
- **Data modeling**: normalizing XBRL `us-gaap` concepts into a tidy long-format table; handling
  missing concepts, multiple units, amended filings, and non-calendar fiscal years
- **Financial analysis**: margin / liquidity / leverage / return ratios, DuPont decomposition,
  year-over-year growth, peer-relative ranking
- **GenAI**: local LLM inference with Ollama, prompt design, grounding output in structured input
- **App + deploy**: Streamlit multi-page app, caching, deployment to Streamlit Community Cloud
- **Engineering hygiene**: `requirements.txt`, `.env`-free config, unit tests on the ratio math,
  a README a stranger can follow

---

## Verified resources

| Resource | URL |
|---|---|
| SEC EDGAR API documentation | https://www.sec.gov/edgar/sec-api-documentation |
| CIK ↔ ticker mapping (JSON) | https://www.sec.gov/files/company_tickers.json |
| Company facts (all XBRL concepts for one filer) | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` |
| Single concept for one filer | `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/[concept].json` |
| One concept across all filers for a period | `https://data.sec.gov/api/xbrl/frames/us-gaap/[concept]/USD/[period].json` |
| Filing history / submissions | `https://data.sec.gov/submissions/CIK##########.json` |
| Ollama (local LLM runtime, free) | https://ollama.com/ |
| Streamlit docs | https://docs.streamlit.io/ |
| Streamlit Community Cloud deploy guide | https://docs.streamlit.io/deploy/streamlit-community-cloud |

**Two API notes that will cost hours if missed.** CIK numbers must be zero-padded to 10 digits in
the URL (Apple is CIK 320193, so `CIK0000320193`). And SEC requires a descriptive `User-Agent`
header identifying you with a contact email; requests without one get blocked. Set it once in your
session object:

```python
session.headers.update({"User-Agent": "Gunnar Austin gunnar.austin@gmail.com"})
```

Cache every raw JSON response to disk on first fetch. `companyfacts` payloads run into the
megabytes, and re-pulling them on every code change is slow and rude to a free public API.

---

## Step-by-step plan

### Milestone 1 — Repo and data access (week of Sept 14, ~4 hrs)

1. `git init` a public repo named `sec-edgar-analyzer`. Add `README.md`, `requirements.txt`, `.gitignore`
   (ignore `data/raw/`), and a `src/` package.
2. Build `src/edgar_client.py`: a `requests.Session` with the User-Agent header, a polite delay
   between calls, retry on 429/503, and a `fetch_json(url)` that caches to `data/raw/`.
3. Pull `company_tickers.json`, build a `ticker -> zero-padded CIK` lookup.
4. Pick your 10 companies and commit the list as `config/companies.yml`. Suggested approach: two
   comparable peer sets of five rather than ten unrelated names, because ratios are only meaningful
   against peers. For example five large-cap software names and five big-box retailers. Avoid mixing
   banks and insurers into a general set; their statements use different concepts and would break a
   shared ratio engine.

**Done when:** one command fetches and caches company facts for all 10 tickers.

### Milestone 2 — Normalize XBRL into a tidy table (week of Sept 21, ~5 hrs)

> Keep this one front-loaded to Mon-Wed. CSE 440 Project 1 is due Friday Sept 25.

1. Write `src/parse.py` to flatten `companyfacts` into one long DataFrame:
   `ticker, concept, unit, fiscal_year, fiscal_period, period_end, value, form, filed, accession`.
2. Map the concepts you need to a stable internal schema. Start with: `Revenues` (and its common
   aliases `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`),
   `GrossProfit`, `OperatingIncomeLoss`, `NetIncomeLoss`, `Assets`, `AssetsCurrent`,
   `Liabilities`, `LiabilitiesCurrent`, `StockholdersEquity`, `CashAndCashEquivalentsAtCarryingValue`,
   `InventoryNet`, `NetCashProvidedByUsedInOperatingActivities`, `PaymentsToAcquirePropertyPlantAndEquipment`,
   `InterestExpense`.
3. Handle the three things that always bite: **concept aliasing** (not every filer tags revenue the
   same way, so resolve a priority list per metric), **restatements** (keep the most recently `filed`
   value for a given `period_end`), and **form filtering** (10-K for annual, 10-Q for quarterly).
4. Write `tests/test_parse.py` with a small committed JSON fixture so the parser is provably correct.

**Done when:** `make data` produces `data/processed/facts.parquet` and the tests pass.

### Milestone 3 — Ratio engine (week of Sept 28, ~4 hrs)

> Deliberately the lightest milestone. CSE 404 HW1 (9/30), CSE 440 Assignment 3 (10/1), and both
> SOIL 203 and TURF 202 Test 1 (10/4) land in this window.

1. `src/ratios.py`, one pure function per ratio, each unit-tested:
   - **Profitability**: gross margin, operating margin, net margin, ROA, ROE
   - **Liquidity**: current ratio, quick ratio
   - **Leverage**: debt-to-equity, interest coverage
   - **Efficiency**: asset turnover
   - **Cash**: free cash flow (CFO − capex), FCF margin
   - **Growth**: YoY revenue and net income growth
2. Add a **DuPont decomposition** (ROE = net margin × asset turnover × equity multiplier). It is
   three lines of code and it is the single most interview-useful thing in the file, because it
   forces you to explain *why* one company's return beats another's.
3. Add peer-relative percentile rank per ratio within each peer set.

**Done when:** `data/processed/ratios.parquet` holds 5 fiscal years × 10 companies × all ratios.

### Milestone 4 — Local LLM narrative layer (week of Oct 5, ~6 hrs)

1. Install Ollama and pull a small instruct model (`llama3.2:3b` or `qwen2.5:7b` — whatever your
   machine handles comfortably; 3B is plenty for summarization).
2. `src/narrate.py`: for each company, serialize **only the computed ratio table** into the prompt
   and ask for a 120-word plain-English summary covering trend, peer standing, and the single
   biggest risk visible in the numbers.
3. **Guardrail the output.** Instruct the model to quote only figures present in the input and to
   write "not available" otherwise. Then verify programmatically: regex every number out of the
   response and assert each one appears in the input table. Log and regenerate on failure. Mention
   this check in your portfolio writeup; it is the detail that separates you from candidates who
   bolted an LLM on and hoped.
4. Cache generated summaries to disk keyed by a hash of the input so the app never needs a GPU at
   runtime. This also means the deployed app works without Ollama, which matters because Community
   Cloud cannot run a local model.

**Done when:** every company has a cached, number-verified summary committed to the repo.

### Milestone 5 — Streamlit app, deploy, and write-up (by Oct 11, ~3 hrs)

1. Three views: **Overview** (peer-set ratio heatmap), **Company** (5-year ratio trend charts,
   DuPont waterfall, the LLM summary), **Data** (the tidy table with a CSV download button).
2. `@st.cache_data` on every load. Read from the committed parquet files, never hit the SEC API at
   request time.
3. Deploy to Streamlit Community Cloud from the public repo. Confirm the URL loads in a private
   window, which catches the "works on my machine" failure.
4. Screenshot the Overview and Company pages for the portfolio entry.

**Done when:** a stranger can open the URL and understand the output without instructions.

---

## Deliverables and how to showcase them

1. **GitHub repo** `github.com/austi20/sec-edgar-analyzer` — README with a screenshot at the top,
   the live app link in the first two lines, a short "design decisions" section (concept aliasing,
   restatement handling, number verification on LLM output), and passing tests.
2. **Live app** — a Streamlit Community Cloud URL. Put it on the resume and the LinkedIn featured
   section. A link that opens instantly outperforms a repo a recruiter will not clone.
3. **Portfolio entry** on austi20.github.io/portfolio/ — one screenshot, three sentences on the
   problem, a list of the ratios computed, and both links.
4. **Suggested resume bullet:**

   > Built a Python pipeline ingesting 10-K/10-Q XBRL filings for 10 public companies via the SEC
   > EDGAR API, normalizing inconsistently tagged `us-gaap` concepts and restated figures into a
   > tidy dataset, then computing 14 financial ratios and DuPont ROE decomposition with unit-tested
   > logic; surfaced results in a deployed Streamlit dashboard with local-LLM narrative summaries
   > validated against source figures to prevent fabricated numbers.

5. **Interview prep** — be ready for these three, they are what a finance interviewer will actually ask:
   - Why does one company's ROE beat a peer's? (DuPont gives you the answer in one sentence.)
   - How did you know your revenue figures were right? (Concept aliasing and restatement logic.)
   - How do you stop an LLM from making up a number? (You verified every digit against the input.)
