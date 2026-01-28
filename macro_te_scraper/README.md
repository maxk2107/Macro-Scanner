# Trading Economics Macro Scraper

This project provides a robust, reproducible way to pull a handful of macro–economic
indicators for a given country from the Trading Economics website or API. When
run, it collects **current**, **previous** and **expected future** values for eight
key U.S. indicators, computes the difference between current and previous and
prints a clean table to the terminal.  The same information is exported to
CSV/JSON, and comprehensive logs are kept for troubleshooting.

## Features

* **Flexible sources** – choose between the official Trading Economics API or
  scraping the public web pages (the scraper is the default and requires no
  API key).
* **Anti‑break design** – selectors are defined declaratively per indicator
  rather than brittle hard‑coded DOM positions.  Should a selector fail,
  debugging information and HTML are saved without crashing the entire run.
* **Politeness** – the scraper waits between requests, uses browser‑like
  headers and retries with exponential backoff on rate limiting errors.
* **Caching** – recently retrieved values are stored on disk to avoid hitting
  Trading Economics repeatedly when run frequently.
* **Validation** – numeric fields are cleaned and checked against sensible
  ranges for each indicator; invalid values are omitted rather than causing
  crashes.
* **Logging** – all activity and errors are logged to a timestamped file
  under `logs/`, and per‑indicator debug HTML is saved under `debug/` when
  needed.
* **Configurable** – adjust the country, list of indicators, timeouts, rate
  limits, headless operation and cache TTL via `config.yaml` without
  changing the code.

## Indicators

The default configuration fetches the following indicators for the United States:

| Indicator             | Description                                  |
|-----------------------|----------------------------------------------|
| **Unemployment**      | Unemployment Rate (%)                        |
| **Inflation MoM**     | Consumer Price Index month‑on‑month (%)      |
| **Interest Rate**     | Fed Funds rate (%)                           |
| **Retail Sales MoM**  | Change in retail sales (%)                   |
| **Services PMI**      | S&P Global services PMI (points)             |
| **Manufacturing PMI** | S&P Global manufacturing PMI (points)        |
| **PPI**               | Producer Price Inflation MoM (%)             |
| **GDP Growth QoQ**    | Quarterly GDP growth rate (%)                |

## Setup

Create a Python virtual environment, install the requirements and run the
scraper.  Below is an example using `venv`, but any environment manager
works:

```bash
# From the project root
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python macro_te_scraper/main.py
```

The script reads `config.yaml` at runtime.  You can override the default
country, choose API vs scraping, provide an API key, adjust timeouts, and
change the list of indicators by editing that file.

## Running

To run with the default configuration (scraping the public pages) simply
execute:

```bash
python macro_te_scraper/main.py
```

On success, the program prints a table like this:

```
Indicator             Current   Previous   Difference   Expected Future
-----------------------------------------------------------------------
Unemployment            4.40        4.50        -0.10            4.50
Inflation MoM           0.30        0.30         0.00            0.10
Interest Rate           3.75        4.00        -0.25            3.75
Retail Sales MoM        0.60       -0.10         0.70            0.50
Services PMI           52.50       52.50         0.00           51.00
Manufacturing PMI      51.90       51.80         0.10           52.00
PPI                     0.20        0.10         0.10            0.50
GDP Growth QoQ          4.40        3.80         0.60            1.80
```

The exact numbers will vary with real‑time data.  The same data is saved to
`output/latest_macro.csv` and `output/latest_macro.json` for downstream use.

## Configuration

The file `config.yaml` controls the behaviour of the scraper.  Here are the
available keys:

```yaml
country: "united-states"         # slug used in Trading Economics URLs
indicators:                      # list of indicator keys as defined in fetcher.py
  - unemployment
  - inflation_mom
  - interest_rate
  - retail_sales_mom
  - services_pmi
  - manufacturing_pmi
  - ppi
  - gdp_growth_qoq
source: "scrape"                 # "api" or "scrape"
api_key: ""                      # your Trading Economics API key (if using API)
timeout_seconds: 30
rate_limit_seconds: 2
headless: true                   # reserved for future browser automation
cache_ttl_minutes: 60            # how long to keep cached values
```

Changing the country or indicators list here will adjust what the scraper
retrieves without code changes.  Note that not all indicators may be
available for every country; scraping selectors may need tuning for other
regions.

## Output

* `output/latest_macro.csv` – CSV with columns:
  `Indicator,Current,Previous,Difference,Expected Future,TimestampUTC,Source`.
* `output/latest_macro.json` – JSON representation of the same data (optional).
* `logs/run_YYYYMMDD_HHMMSS.log` – detailed log of the run.
* `debug/` – if an indicator fails to scrape, the offending HTML is saved
  here for inspection.

## Extending

To add new indicators or support additional countries, update the
`INDICATOR_MAP` in `fetcher.py` with the appropriate URL paths and selectors.
For API usage, refer to the official Trading Economics docs to construct the
correct endpoints.
