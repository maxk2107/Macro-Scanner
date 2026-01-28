"""Simple GUI application for the Trading Economics macro scraper.

This GUI uses Tkinter to present a small window with a single button
that triggers the macro scraping process.  When the button is clicked,
the script runs the same logic as `main.py`, fetching data for
all configured countries and indicators, writing CSV/JSON outputs,
and logging the results.  A dialog box informs the user of
success or failure.

To build a standalone Mac application, you can use `pyinstaller` or
`py2app`.  See the project README for guidance on packaging.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
import sys

# Try to import `run` from the package (when installed) first.  Fall back
# to relative import when run inside the project directory.
try:
    from macro_te_scraper.src.fetcher import run  # type: ignore
except ModuleNotFoundError:
    from src.fetcher import run  # type: ignore


def on_run_clicked() -> None:
    """Callback triggered when the user clicks the run button."""
    try:
        exit_code = run()
        if exit_code == 0:
            message = (
                "Macro data fetched successfully. \n\n"
                "Outputs have been saved to the `output` directory."
            )
        else:
            message = (
                "Macro data fetch completed with some errors.\n\n"
                "Please check the logs in the `logs` directory for details."
            )
        messagebox.showinfo("Macro Scraper", message)
    except Exception as exc:
        # Display unexpected exceptions to the user
        messagebox.showerror("Error", f"An unexpected error occurred:\n{exc}")


def main() -> None:
    """Create and run the Tkinter GUI application."""
    root = tk.Tk()
    root.title("Trading Economics Macro Scraper")
    # Center and size the window reasonably
    root.geometry("400x150")
    # Create a label with instructions
    label = tk.Label(
        root,
        text=(
            "Click the button below to fetch macroeconomic data\n"
            "for the configured countries and indicators."
        ),
        justify="center",
    )
    label.pack(pady=(20, 10))
    # Create the run button
    button = tk.Button(
        root,
        text="Fetch Macro Data",
        width=20,
        height=2,
        command=on_run_clicked,
    )
    button.pack()
    # Start the Tkinter event loop
    root.mainloop()


if __name__ == "__main__":
    main()