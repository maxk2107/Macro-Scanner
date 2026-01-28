"""Scraping Trading Economics public pages for indicator data.

This module implements a resilient scraper that collects current, previous and
expected future values for a set of macro indicators from Trading Economics.
It uses `requests` and `BeautifulSoup` for parsing static HTML.  If
JavaScript rendering is required in the future, the structure allows
extending to headless browsers (e.g. Playwright) while retaining the same
interface.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from ..parsing.cleaners import parse_value


class TradingEconomicsScraper:
    """Scraper for Trading Economics indicators."""

    BASE_URL = "https://tradingeconomics.com"

    def __init__(
        self,
        country_slug: str,
        indicator_map: Dict[str, Dict[str, str]],
        timeout: int,
        rate_limit: float,
        logger,
        base_dir: Path,
    ) -> None:
        self.country = country_slug
        self.indicator_map = indicator_map
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.logger = logger
        self.base_dir = base_dir
        self.session = requests.Session()
        # Browser‑like headers
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/119.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def _request(self, url: str) -> Optional[str]:
        """Fetch a URL with retries and rate limiting.

        Returns the text content on success or ``None`` on failure.
        """
        last_exception = None
        delay = self.rate_limit
        for attempt in range(5):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                status = resp.status_code
                if status == 200:
                    time.sleep(self.rate_limit)
                    return resp.text
                if status in (429, 500, 502, 503, 504):
                    self.logger.warning(
                        "Received HTTP %s for %s (attempt %d), retrying after %.1fs",
                        status,
                        url,
                        attempt + 1,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                else:
                    self.logger.error("HTTP %s for %s", status, url)
                    return None
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    "Error fetching %s on attempt %d: %s", url, attempt + 1, str(e)
                )
                time.sleep(delay)
                delay *= 2
        if last_exception:
            self.logger.error("Failed to fetch %s: %s", url, str(last_exception))
        return None

    def fetch_indicators_page(self) -> Optional[BeautifulSoup]:
        """Retrieve and parse the country's indicators page."""
        url = f"{self.BASE_URL}/{self.country}/indicators"
        html = self._request(url)
        if html is None:
            self._save_debug("indicators_page", url, "failed to fetch indicators page", html)
            return None
        soup = BeautifulSoup(html, "html.parser")
        return soup

    def _find_row(self, soup: BeautifulSoup, slug: str, row_label: str) -> Optional[List[str]]:
        """Locate the table row for an indicator.

        The function first tries to find an anchor whose href contains the slug.
        If not found, it falls back to searching for a link with matching text
        (row_label).

        Returns a list of cell texts if found, else None.
        """
        # 1. Try by slug
        try:
            anchor = soup.find(
                "a", href=lambda h: isinstance(h, str) and f"/{self.country}/{slug}" in h
            )
            if anchor:
                tr = anchor.find_parent("tr")
                if tr:
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    return cells
        except Exception:
            pass
        # 2. Fallback by row_label
        try:
            anchor = soup.find("a", string=lambda t: isinstance(t, str) and row_label.lower() in t.lower())
            if anchor:
                tr = anchor.find_parent("tr")
                if tr:
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    return cells
        except Exception:
            pass
        return None

    def fetch_expected_and_trend(
        self, expected_url: str
    ) -> Tuple[Optional[float], Optional[str], Optional[List[float]]]:
        """
        Fetch and parse the expected future value, next release date, and a 6‑month trend
        from an indicator page.

        Parameters
        ----------
        expected_url : str
            Relative URL of the indicator page (e.g., "united-states/inflation-rate-mom").

        Returns
        -------
        tuple
            (expected_value, next_release_date_str, trend_list)
            Where `expected_value` is a float or None, `next_release_date_str` is a
            string as found on the page (e.g., "Jan 15"), and `trend_list` is a list of
            up to six floats representing the most recent actual values.
        """
        url = f"{self.BASE_URL}/{expected_url}"
        html = self._request(url)
        if html is None:
            self.logger.error("Failed to fetch expected value page %s", url)
            self._save_debug(expected_url.replace("/", "_"), url, "failed expected page", html)
            return None, None, None
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        expected: Optional[float] = None
        next_release: Optional[str] = None
        trend: Optional[List[float]] = None
        # 1. Look for phrase "is expected to be X"
        m = re.search(
            r"is\s+expected\s+to\s+be\s+([-+]?[0-9]*\.?[0-9]+)",
            text,
            re.IGNORECASE,
        )
        if m:
            raw_number = m.group(1)
            try:
                expected = parse_value(raw_number)
            except Exception:
                expected = None
        else:
            # Fallback: parse consensus or TEForecast from the calendar section
            # The calendar table typically contains rows like: Date GMT Reference Actual Previous Consensus TEForecast
            # We'll extract the first row (most recent or next release) for expected values.
            # Parse the table from HTML.
            cal_expected, cal_next, cal_trend = self._parse_calendar(soup)
            if cal_expected is not None:
                expected = cal_expected
            if cal_next:
                next_release = cal_next
            if cal_trend:
                trend = cal_trend
        # Even if primary expected was found, still attempt to extract trend and next release from calendar
        if trend is None or next_release is None:
            _, nr, tr = self._parse_calendar(soup)
            if next_release is None:
                next_release = nr
            if trend is None:
                trend = tr
        return expected, next_release, trend

    def _parse_calendar(
        self, soup: BeautifulSoup
    ) -> Tuple[Optional[float], Optional[str], Optional[List[float]]]:
        """
        Parse the calendar table to extract an expected value (consensus or TEForecast),
        the next release date, and a trend list of recent actual values.

        Returns
        -------
        tuple
            (expected_value, next_release_date_str, trend_list)
        """
        expected: Optional[float] = None
        next_release: Optional[str] = None
        trend: List[float] = []
        try:
            table = soup.find("table", id=lambda x: x and "calendar" in x.lower())
            if not table:
                return None, None, None
            rows = table.find_all("tr")
            # Skip header row; gather up to 6 actual values
            for tr in rows[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if not cells:
                    continue
                # cells structure: [Date, GMT, Reference, Actual, Previous, Consensus, TEForecast]
                # 1. Collect trend from actual column if numeric
                # Use first 6 numeric actuals
                if len(trend) < 6:
                    if len(cells) >= 4:
                        actual_str = cells[3]
                        try:
                            val = parse_value(actual_str)
                            if val is not None:
                                trend.append(val)
                        except Exception:
                            pass
                # 2. Determine if this row is the next release: actual cell missing or contains non‑numeric
                if next_release is None:
                    if len(cells) >= 4:
                        actual_str = cells[3]
                        try:
                            _ = parse_value(actual_str)
                            # numeric actual: already released; skip for next release
                        except Exception:
                            # Not numeric -> this is upcoming release row
                            # Next release date is in first cell
                            next_release = cells[0]
                            # Consensus or forecast for expected value
                            consensus = cells[5] if len(cells) > 5 else ""
                            teforecast = cells[6] if len(cells) > 6 else ""
                            try:
                                if teforecast:
                                    expected = parse_value(teforecast)
                                elif consensus:
                                    expected = parse_value(consensus)
                            except Exception:
                                pass
                # Break early if we collected 6 trends and found next_release
                if len(trend) >= 6 and next_release is not None:
                    break
            # Ensure trend list has up to 6 values
            if trend:
                trend = trend[:6]
            return expected, next_release, trend if trend else None
        except Exception as e:
            self.logger.debug("Error parsing calendar table: %s", e)
        return None, None, None

    def fetch_all(self, indicator_keys: List[str]) -> Dict[str, Dict[str, Optional[float]]]:
        """Fetch current, previous and expected values for all requested indicators.

        Parameters
        ----------
        indicator_keys : list of str
            Keys corresponding to entries in ``self.indicator_map``.

        Returns
        -------
        dict
            Mapping from indicator key to a dict with keys ``current``, ``previous``
            and ``expected`` (floats or None).
        """
        results: Dict[str, Dict[str, Optional[float]]] = {}
        soup = self.fetch_indicators_page()
        if soup is None:
            # If page fetch fails, return empty results
            return results
        for key in indicator_keys:
            # Look up indicator definition.  Skip if missing.
            info = self.indicator_map.get(key)
            if not info:
                self.logger.warning("Indicator %s not found in mapping", key)
                continue
            slug: str | None = info.get("slug")
            row_label: str | None = info.get("row_label")
            # Build expected URL dynamically: combine country and slug
            expected_url: Optional[str] = None
            if slug:
                expected_url = f"{self.country}/{slug}"
            current = previous = expected = None
            published: Optional[str] = None
            next_release: Optional[str] = None
            # Parse current and previous from the country indicators page
            try:
                cells = self._find_row(soup, slug, row_label)
                if cells and len(cells) >= 3:
                    # cells[1] -> last/current, cells[2] -> previous
                    current = parse_value(cells[1])
                    previous = parse_value(cells[2])
                    # Attempt to extract reference date (published date) from last cell
                    if len(cells) >= 5:
                        ref = cells[-1]
                        # Parse month/year reference like "Dec/25" or "Dec 2025"
                        ref_clean = ref.replace(" ", "").replace("\xa0", "")
                        try:
                            # Match format like Dec/25
                            mref = re.match(r"([A-Za-z]+)/(\d{2})", ref_clean)
                            if mref:
                                mon = mref.group(1)[:3].title()
                                year_suffix = int(mref.group(2))
                                year = 2000 + year_suffix if year_suffix < 70 else 1900 + year_suffix
                                month = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].index(mon) + 1
                                published = f"{year:04d}-{month:02d}-01"
                            else:
                                # Match format like Dec2025 or Dec2025
                                mref2 = re.match(r"([A-Za-z]+)(\d{4})", ref_clean)
                                if mref2:
                                    mon = mref2.group(1)[:3].title()
                                    year = int(mref2.group(2))
                                    month = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].index(mon) + 1
                                    published = f"{year:04d}-{month:02d}-01"
                        except Exception:
                            pass
                    self.logger.debug("%s row cells: %s", key, cells)
                else:
                    self.logger.error("Row for %s not found or malformed", key)
            except Exception as e:
                self.logger.error("Error parsing row for %s: %s", key, e)
            # Fetch expected value, next release, and trend by visiting the indicator's dedicated page
            trend_values: Optional[List[float]] = None
            if expected_url:
                try:
                    expected_value, next_rel, trend_values = self.fetch_expected_and_trend(
                        expected_url
                    )
                    if expected_value is not None:
                        expected = expected_value
                    # Override next_release if found on page
                    if next_rel:
                        next_release = next_rel
                except Exception as e:
                    self.logger.error("Error parsing expected/trend for %s: %s", key, e)
            # Store results (values may be None if missing)
            results[key] = {
                "current": current,
                "previous": previous,
                "expected": expected,
                "published": published,
                "next_release": next_release,
                "trend": trend_values,
            }
        return results

    def _save_debug(self, name: str, url: str, reason: str, html: Optional[str]) -> None:
        """Save debug HTML to the debug directory for failed scrapes."""
        debug_dir = self.base_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = debug_dir / f"{name}_{timestamp}.html"
        try:
            with filename.open("w", encoding="utf-8") as f:
                f.write(f"<!-- URL: {url} -->\n<!-- Reason: {reason} -->\n")
                if html:
                    f.write(html)
            self.logger.debug("Saved debug HTML to %s", filename)
        except Exception as e:
            self.logger.error("Failed to save debug HTML for %s: %s", name, e)
