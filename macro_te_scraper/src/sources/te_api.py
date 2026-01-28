"""Trading Economics API client.

This module provides a minimal wrapper around the Trading Economics API.  It
attempts to fetch the latest, previous and forecast values for a given
indicator.  An API key is required; you can obtain one by registering on
Trading Economics.  Without a valid key, the API will return 403 errors.

Note: The API is not directly exercised in this project because a key is
necessary.  The code is included for completeness and may need adjustment
depending on the exact API responses.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests


class TradingEconomicsAPI:
    BASE_URL = "https://api.tradingeconomics.com"

    def __init__(self, api_key: str, timeout: int, rate_limit: float, logger) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/119.0 Safari/537.36",
                "Accept": "application/json",
            }
        )

    def _request(self, endpoint: str) -> Optional[List[Dict]]:
        url = f"{self.BASE_URL}{endpoint}"
        delay = self.rate_limit
        for attempt in range(5):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    time.sleep(self.rate_limit)
                    return resp.json()
                if resp.status_code in (429, 500, 502, 503, 504):
                    self.logger.warning(
                        "API HTTP %s for %s, retrying", resp.status_code, url
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                self.logger.error("API request %s failed with status %s", url, resp.status_code)
                return None
            except Exception as e:
                self.logger.warning("API request error for %s: %s", url, str(e))
                time.sleep(delay)
                delay *= 2
        return None

    def fetch_all(self, country: str, indicator_map: Dict[str, Dict[str, str]], indicator_keys: List[str]) -> Dict[str, Dict[str, Optional[float]]]:
        """Fetch all indicators using the API.

        Returns a dict mapping indicator keys to a dict with current, previous and expected values.
        The expected field comes from the API's `teforecast` field if available.
        """
        result: Dict[str, Dict[str, Optional[float]]] = {}
        # Fetch all indicator data for the country
        endpoint = f"/country/{country}?c={self.api_key}"
        data = self._request(endpoint)
        if not data:
            return result
        # Build a mapping from category names to values
        # Each item in data is expected to have keys: 'category', 'latestValue', 'previousValue', 'teforecast'
        lookup: Dict[str, Dict[str, Optional[float]]] = {}
        for item in data:
            category = item.get("category")
            if not category:
                continue
            latest_value = item.get("latestValue")
            previous_value = item.get("previousValue")
            forecast = item.get("teforecast") or item.get("forecast")
            try:
                latest_value = float(latest_value) if latest_value is not None else None
            except Exception:
                latest_value = None
            try:
                previous_value = float(previous_value) if previous_value is not None else None
            except Exception:
                previous_value = None
            try:
                forecast = float(forecast) if forecast is not None else None
            except Exception:
                forecast = None
            lookup[category.lower()] = {
                "current": latest_value,
                "previous": previous_value,
                "expected": forecast,
            }
        # Map requested indicators
        for key in indicator_keys:
            info = indicator_map.get(key)
            if not info:
                continue
            category = info.get("row_label", "").lower()
            res = lookup.get(category)
            if res:
                result[key] = res
            else:
                self.logger.error("API data for %s not found", category)
                result[key] = {"current": None, "previous": None, "expected": None}
        return result
