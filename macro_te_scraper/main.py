"""Entry point for the Trading Economics macro scraper.

This script simply forwards to :func:`macro_te_scraper.src.fetcher.run` and
exits with the returned status code.  It exists as a thin wrapper to allow
`python main.py` execution from the project root without manipulating
PYTHONPATH.
"""

import sys

try:
    # When executed via `python -m macro_te_scraper.main` from parent directory,
    # import using the package name.
    from macro_te_scraper.src.fetcher import run  # type: ignore
except ModuleNotFoundError:
    # When executed via `python main.py` from within the macro_te_scraper folder,
    # fall back to a relative import.
    from src.fetcher import run  # type: ignore


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
