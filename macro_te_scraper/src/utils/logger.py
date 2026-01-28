"""Logging utilities for the macro scraper.

This module centralises logger configuration.  A timestamped log file is
created in the `logs/` directory, and messages are also sent to the console
with a simple format.  Call :func:`setup_logger` once at program start and
use the returned logger throughout your code.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_logger(base_dir: Path, name: str = "macro_scraper") -> logging.Logger:
    """Set up and return a logger instance.

    Parameters
    ----------
    base_dir : Path
        Base directory of the project (typically the parent of `src`).  Log
        files will be placed under `logs/` relative to this directory.
    name : str, optional
        Name of the logger to create.  Defaults to ``"macro_scraper"``.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    # Ensure logs directory exists
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"run_{timestamp}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(file_format)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    console_format = logging.Formatter("%(message)s")
    ch.setFormatter(console_format)
    logger.addHandler(ch)

    logger.debug("Logger initialised. Log file: %s", log_file)
    return logger
