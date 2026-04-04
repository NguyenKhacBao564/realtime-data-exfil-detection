"""
src/utils/helpers.py — Logging setup and utility helpers.
"""

import logging
import sys
from pathlib import Path
from src.utils.config import LOG_FILE, LOG_LEVEL


def setup_logging(level: str = None) -> logging.Logger:
    """
    Setup thread-safe logging for the pipeline.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    level = level or LOG_LEVEL
    log_file = LOG_FILE

    # Create formatter
    fmt = "%(asctime)s %(levelname)-8s — %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=date_fmt)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    # File handler
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root_logger.addHandler(fh)

    # Console handler (colored for alerts)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)

    return root_logger


def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name or "exfil")


# =============================================================================
# General helpers
# =============================================================================

def safe_div(a: float, b: float, default: float = 0.0) -> float:
    """Safe division — returns default if b is zero or invalid."""
    if b is None or b == 0 or not isinstance(b, (int, float)):
        return default
    if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return default
    try:
        result = a / b
        if not (-1e308 < result < 1e308):  # catch inf
            return default
        return result
    except (ZeroDivisionError, FloatingPointError):
        return default


def clip_inf(series, fill_value: float = 0.0) -> "pd.Series":
    """
    Replace inf/-inf/nan values in a pandas Series.
    Requires pandas to be imported in calling scope.
    """
    import pandas as pd
    import numpy as np
    series = series.replace([np.inf, -np.inf], np.nan)
    series = series.fillna(fill_value)
    return series


def normalize_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Normalize column names: strip whitespace, remove duplicate columns.
    Fixes the inconsistent space-prefix issue in CICIDS2017 CSV files.
    """
    import pandas as pd
    df.columns = df.columns.str.strip()
    # Remove duplicate columns (keep first)
    df = df.loc[:, ~df.columns.duplicated()]
    return df
