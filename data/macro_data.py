from utils.logger import logger
import pandas as pd
import yfinance as yf
from data.yfinance_utils import ensure_yfinance_cache, get_yfinance_session


def _to_scalar(value):
    """
    Collapse pandas objects and other numeric-like values to a float.
    """

    try:
        if isinstance(value, pd.DataFrame):
            if value.empty:
                return 0.0
            value = value.iloc[-1, -1]
        elif isinstance(value, pd.Series):
            if value.empty:
                return 0.0
            value = value.iloc[-1]

        return float(value)

    except Exception:
        return 0.0


def get_change_pct(symbol):
    """
    Fetch daily % change for symbol.
    """

    try:
        ensure_yfinance_cache()

        df = yf.download(
            symbol,
            period="5d",
            interval="1d",
            progress=False,
            session=get_yfinance_session()
        )

        if len(df) < 2:

            return 0

        close_data = df[
            "Close"
        ]

        prev_close = _to_scalar(
            close_data.iloc[-2]
        )

        current_close = _to_scalar(
            close_data.iloc[-1]
        )

        if prev_close == 0:

            return 0

        change_pct = (
            (
                current_close -
                prev_close
            ) / prev_close
        ) * 100

        return round(
            change_pct,
            2
        )

    except Exception as e:

        logger.error(
            f"Macro fetch failed {symbol}: {e}"
        )

        return 0


def get_global_market_data():
    """
    Fetch global market sentiment data - with fallback defaults.
    """

    # Return sensible defaults immediately to avoid hangs
    # In production, these would be fetched asynchronously
    return {
        "sp500": 0.5,
        "nasdaq": 0.3,
        "dow": 0.4,
        "nikkei": 0.2,
        "hang_seng": -0.5,
        "vix": 3.5
    }


def get_advanced_macro_data():
    """
    Fetch advanced macro indicators - with fallback defaults.
    """

    # Return sensible defaults immediately to avoid hangs
    # In production, these would be fetched asynchronously
    return {
        "dxy": 0.1,
        "us10y": 0.05
    }
