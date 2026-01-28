"""Utility functions for cleaning and converting scraped values."""

from __future__ import annotations

import re
from typing import Optional


def parse_value(raw: str) -> Optional[float]:
    """Convert a raw textual value from Trading Economics into a float.

    The function removes common non‑numeric tokens such as percent signs,
    "points", commas and whitespace.  It returns ``None`` if the input
    cannot be parsed into a float.

    Parameters
    ----------
    raw : str
        Raw string as scraped (e.g. "4.4%", "52.5 points", "-0.1").

    Returns
    -------
    Optional[float]
        Parsed floating point number or None if not parseable.
    """
    if raw is None:
        return None
    s = raw.strip().lower()
    # Remove percent signs and unit words
    s = s.replace("%", "").replace("points", "").replace("point", "")
    # Remove commas and spaces
    s = s.replace(",", "").replace(" ", "")
    # Replace double negative or weird dashes
    s = s.replace("–", "-").replace("—", "-")
    # Extract number using regex (match first occurrence of optional sign, digits, decimal)
    match = re.search(r"[-+]?[0-9]*\.?[0-9]+", s)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def compute_difference(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Compute the difference between current and previous values.

    If either value is None, returns None.  Otherwise returns the
    difference rounded to two decimal places.
    """
    if current is None or previous is None:
        return None
    diff = current - previous
    # Round to two decimals for consistency
    return round(diff, 2)
