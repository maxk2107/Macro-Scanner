"""Table and file output utilities."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

def _compute_widths(rows: List[List[str]], headers: List[str]) -> List[int]:
    """Compute the maximum width for each column.

    Parameters
    ----------
    rows : list of lists of str
        Table body rows.
    headers : list of str
        Table headers.

    Returns
    -------
    list of int
        Width of each column.
    """
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    return widths


def print_and_save(
    rows: List[Dict[str, Optional[float]]],
    base_dir: Path,
    source: str,
    save_json: bool = True,
) -> None:
    """Print the results table to stdout and save CSV/JSON files.

    Parameters
    ----------
    rows : list of dict
        Each dict must contain the keys: Indicator, Current, Previous,
        Difference, Expected Future.
    base_dir : Path
        Root directory of the project.  Files will be saved under
        ``output/`` relative to this directory.
    source : str
        Either ``"api"`` or ``"scrape"`` to record in the output file.
    save_json : bool, optional
        Whether to save a JSON file alongside the CSV.  Defaults to True.
    """
    if not rows:
        print("No data to display.")
        return
    # Determine which extra fields are present
    base_fields = ["Indicator", "Current", "Previous", "Difference", "Expected Future"]
    extra_fields = []
    for field in ["Surprise", "Published", "Next Release"]:
        if field in rows[0]:
            extra_fields.append(field)
    # Prepare printable rows
    printable_rows: List[List[str]] = []
    for row in rows:
        row_values: List[str] = []
        # Indicator, current, previous, difference, expected
        row_values.append(row.get("Indicator", ""))
        row_values.append(_format_number(row.get("Current")))
        row_values.append(_format_number(row.get("Previous")))
        row_values.append(_format_number(row.get("Difference")))
        row_values.append(_format_number(row.get("Expected Future")))
        # Extra fields
        for field in extra_fields:
            value = row.get(field)
            # Format numbers for Surprise
            if field == "Surprise":
                row_values.append(_format_number(value))
            else:
                row_values.append(str(value) if value is not None else "")
        printable_rows.append(row_values)
    # Determine headers
    if "Country" in rows[0]:
        headers = ["Country"] + base_fields + extra_fields
        # Prepend country values to printable rows
        printable_rows = [
            [r.get("Country", "")] + row for r, row in zip(rows, printable_rows)
        ]
    else:
        headers = base_fields + extra_fields
    widths = _compute_widths(printable_rows, headers)

    # Print header
    header_line = " ".join(
        h.ljust(widths[i]) if i == 0 else h.rjust(widths[i]) for i, h in enumerate(headers)
    )
    print(header_line)
    # Underline
    print(" ".join("-" * w for w in widths))
    # Print rows
    for row in printable_rows:
        # Build each line with left alignment for the first column and right alignment for the rest
        line_parts: List[str] = []
        for i in range(len(headers)):
            cell = row[i]
            if i == 0:
                line_parts.append(cell.ljust(widths[i]))
            else:
                line_parts.append(cell.rjust(widths[i]))
        print(" ".join(line_parts))

    # Save CSV
    output_dir = base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    csv_path = output_dir / "latest_macro.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Determine CSV headers including extra fields
        extra_fields = []
        for field in ["Surprise", "Published", "Next Release"]:
            if field in rows[0]:
                extra_fields.append(field)
        if "Country" in rows[0]:
            csv_headers = [
                "Country",
                "Indicator",
                "Current",
                "Previous",
                "Difference",
                "Expected Future",
            ] + extra_fields + ["TimestampUTC", "Source"]
        else:
            csv_headers = [
                "Indicator",
                "Current",
                "Previous",
                "Difference",
                "Expected Future",
            ] + extra_fields + ["TimestampUTC", "Source"]
        writer.writerow(csv_headers)
        for row in rows:
            row_list = []
            if "Country" in row:
                row_list.append(row.get("Country", ""))
            row_list.extend([
                row.get("Indicator", ""),
                row.get("Current", ""),
                row.get("Previous", ""),
                row.get("Difference", ""),
                row.get("Expected Future", ""),
            ])
            # Add extra fields values
            for field in extra_fields:
                row_list.append(row.get(field, ""))
            row_list.extend([timestamp, source])
            writer.writerow(row_list)
    if save_json:
        json_path = output_dir / "latest_macro.json"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump({"timestamp": timestamp, "source": source, "data": rows}, f, indent=2)


def _format_number(value: Optional[float]) -> str:
    """Format numeric values for display.

    None values are returned as empty strings; integers are displayed without
    decimal places; floats are shown with two decimals.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        # Decide whether to display decimals
        if value == int(value):
            return f"{int(value)}"
        return f"{value:.2f}"
    return str(value)
