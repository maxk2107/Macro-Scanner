"""Validation of numeric ranges for macro indicators.

The rules here ensure that obviously erroneous numbers (e.g. 9999% inflation)
are not ingested.  Each indicator has a plausible minimum and maximum value.
Values falling outside this range are treated as invalid and replaced with
``None``.
"""

from __future__ import annotations

from typing import Optional, Tuple


# Lower and upper bounds for each indicator.  These ranges were chosen
# conservatively to flag only truly impossible values.  If you add new
# indicators, please update this mapping accordingly.
INDICATOR_RANGES = {
    "unemployment": (0, 30),
    "inflation_mom": (-10, 10),
    # Year-over-year inflation can vary widely; use a broad but plausible range
    "inflation_yoy": (-10, 50),
    "interest_rate": (0, 30),
    "retail_sales_mom": (-50, 50),
    # Year-over-year retail sales growth; allow larger swings
    "retail_sales_yoy": (-50, 100),
    "services_pmi": (0, 100),
    "manufacturing_pmi": (0, 100),
    "ppi": (-20, 20),
    "gdp_growth_qoq": (-50, 50),
}


def validate(indicator: str, value: Optional[float]) -> Optional[float]:
    """Validate a numeric value against the predefined range for an indicator.

    Parameters
    ----------
    indicator : str
        Key of the indicator (e.g. "unemployment").
    value : Optional[float]
        Value to validate.

    Returns
    -------
    Optional[float]
        The value if it falls within the allowed range, otherwise ``None``.
    """
    if value is None:
        return None
    bounds: Tuple[float, float] = INDICATOR_RANGES.get(indicator, (-float("inf"), float("inf")))
    lo, hi = bounds
    if lo <= value <= hi:
        return value
    return None
