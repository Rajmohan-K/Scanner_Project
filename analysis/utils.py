from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def scalar(value: Any, default: float = 0.0) -> float:
    """Convert a single-value pandas/numpy object to a float."""
    try:
        if isinstance(value, pd.Series):
            value = value.dropna()
            if value.empty:
                return default
            return float(value.iloc[-1])
        if isinstance(value, pd.Index):
            if value.empty:
                return default
            return float(value[-1])
        if isinstance(value, np.ndarray):
            flattened = value.flatten()
            if flattened.size == 0:
                return default
            return float(flattened[-1])
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def latest_value(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    if df is None or df.empty or column not in df.columns:
        return default
    return scalar(df[column], default=default)


def has_columns(df: pd.DataFrame, columns: list[str]) -> bool:
    return df is not None and not df.empty and all(column in df.columns for column in columns)
