"""Top‑level orchestrator for pulling macro indicators.

This module reads configuration from `config.yaml`, instantiates either the
API client or the scraper, applies caching and validation, and prepares
structured output.  It does not perform any I/O besides logging and is
invoked by `main.py`.
"""

from __future__ import annotations

import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional

from .utils.logger import setup_logger
from .utils.cache import Cache
from .parsing.cleaners import compute_difference
from .parsing.validators import validate
from .utils.table import print_and_save
from .sources.te_scrape import TradingEconomicsScraper
from .sources.te_api import TradingEconomicsAPI


def load_config(config_path: Path) -> Dict:
    """Load YAML configuration file."""
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run() -> int:
    """Main entry point for running the scraper.  Returns exit code."""
    # Determine base directory (two levels up from this file)
    base_dir = Path(__file__).resolve().parents[1]
    config_path = base_dir / "config.yaml"
    config = load_config(config_path)
    logger = setup_logger(base_dir)
    # Support multiple countries.  If 'countries' is provided in config, use that
    # list; otherwise fall back to single 'country'.
    if isinstance(config.get("countries"), list) and config.get("countries"):
        countries: List[str] = [str(c).lower() for c in config.get("countries")]
    else:
        countries = [str(config.get("country", "united-states")).lower()]
    indicator_keys: List[str] = config.get("indicators", [])
    source = config.get("source", "scrape").lower()
    api_key = config.get("api_key", "")
    timeout = int(config.get("timeout_seconds", 30))
    rate_limit = float(config.get("rate_limit_seconds", 2))
    cache_ttl = int(config.get("cache_ttl_minutes", 60))

    # Indicator mapping central definition – names, slugs and expected URLs
    # Define indicator metadata.  Do not reference `country` here because it is
    # set only within the loop below.  Expected values will be fetched by
    # combining the country and the indicator slug inside the scraper.
    INDICATOR_MAP: Dict[str, Dict[str, str]] = {
        "unemployment": {
            "name": "Unemployment",
            "row_label": "Unemployment Rate",
            "slug": "unemployment-rate",
        },
        "inflation_mom": {
            "name": "Inflation MoM",
            "row_label": "Inflation Rate MoM",
            "slug": "inflation-rate-mom",
        },
        # Year-over-year inflation (annual inflation rate)
        "inflation_yoy": {
            "name": "Inflation YoY",
            "row_label": "Inflation Rate",
            # tradingeconomics slug for inflation rate (CPI YoY). TE uses 'inflation-cpi'
            "slug": "inflation-cpi",
        },
        "interest_rate": {
            "name": "Interest Rate",
            "row_label": "Interest Rate",
            "slug": "interest-rate",
        },
        "retail_sales_mom": {
            "name": "Retail Sales MoM",
            "row_label": "Retail Sales MoM",
            "slug": "retail-sales-mom",
        },
        # Year-over-year retail sales
        "retail_sales_yoy": {
            "name": "Retail Sales YoY",
            "row_label": "Retail Sales YoY",
            "slug": "retail-sales-yoy",
        },
        "services_pmi": {
            "name": "Services PMI",
            "row_label": "Services PMI",
            "slug": "services-pmi",
        },
        "manufacturing_pmi": {
            "name": "Manufacturing PMI",
            "row_label": "Manufacturing PMI",
            "slug": "manufacturing-pmi",
        },
        "ppi": {
            "name": "PPI",
            "row_label": "Producer Price Inflation MoM",
            "slug": "producer-price-inflation-mom",
        },
        "gdp_growth_qoq": {
            "name": "GDP Growth QoQ",
            "row_label": "GDP Growth Rate",
            "slug": "gdp-growth",
        },
    }

    # Prepare cache (one file for all countries)
    cache_file = base_dir / "output" / "cache.json"
    cache = Cache(cache_file, ttl_minutes=cache_ttl)

    rows = []
    successes = 0
    # Iterate through each country
    for country in countries:
        # Determine source-specific client per country (for API we reuse same client but pass country later)
        if source == "api":
            if not api_key:
                logger.error("API source selected but no api_key provided in config.")
                return 1
            client_api = TradingEconomicsAPI(api_key, timeout, rate_limit, logger)
            data_map = client_api.fetch_all(country, INDICATOR_MAP, indicator_keys)
        else:
            scraper = TradingEconomicsScraper(country, INDICATOR_MAP, timeout, rate_limit, logger, base_dir)
            data_map = scraper.fetch_all(indicator_keys)
        # Process each indicator for this country
        for key in indicator_keys:
            info = INDICATOR_MAP.get(key)
            if not info:
                logger.warning("No mapping found for indicator %s", key)
                continue
            cache_key = f"{country}:{key}"
            cached = cache.get(cache_key)
            if cached:
                values = cached
                logger.debug("Using cached values for %s (%s)", key, country)
            else:
                # Default structure ensures keys exist
                values = data_map.get(key) or {
                    "current": None,
                    "previous": None,
                    "expected": None,
                    "published": None,
                    "next_release": None,
                    "trend": None,
                }
                cache.set(cache_key, values)
            current = validate(key, values.get("current"))
            previous = validate(key, values.get("previous"))
            expected = validate(key, values.get("expected"))
            published = values.get("published")
            next_release = values.get("next_release")
            trend = values.get("trend")  # list or None
            diff = compute_difference(current, previous)
            surprise = compute_difference(current, expected) if expected is not None else None
            if current is not None:
                successes += 1
            row_dict = {
                "Country": country,
                "Indicator": info["name"],
                "Current": current,
                "Previous": previous,
                "Difference": diff,
                "Expected Future": expected,
                "Surprise": surprise,
                "Published": published,
                "Next Release": next_release,
            }
            # Include trend if available
            if trend is not None:
                row_dict["Trend"] = trend
            rows.append(row_dict)
    # Print and save table
    print_and_save(rows, base_dir, source)
    # Determine exit code: success if at least 75% of indicator-country combos have current values
    total_needed = len(countries) * len(indicator_keys)
    return 0 if successes >= max(1, int(0.75 * total_needed)) else 1


if __name__ == "__main__":
    sys.exit(run())
