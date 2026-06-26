from utils.logger import logger
import yfinance as yf
import pandas as pd
from data.yfinance_utils import ensure_yfinance_cache, get_yfinance_session


# ==========================
# Stock → Sector Mapping
# ==========================
STOCK_SECTOR_MAP = {

    "RELIANCE.NS": "ENERGY",

    "INFY.NS": "IT",

    "TCS.NS": "IT",

    "HDFCBANK.NS": "BANKING",

    "ICICIBANK.NS": "BANKING",

    "SBIN.NS": "BANKING"
}


# ==========================
# Sector → Benchmark Symbol
# ==========================
SECTOR_SYMBOL_MAP = {

    "IT": "^CNXIT",

    "BANKING": "^NSEBANK",

    "ENERGY": "^CNXENERGY"
}


def get_stock_sector(
    symbol
):
    """
    Return sector for stock.
    """

    return STOCK_SECTOR_MAP.get(
        symbol,
        None
    )


def get_sector_symbol(
    sector
):
    """
    Return benchmark ticker for sector.
    """

    return SECTOR_SYMBOL_MAP.get(
        sector,
        None
    )


def get_sector_data(
    stock_symbol,
    period="6mo",
    interval="1d"
):
    """
    Fetch sector OHLC data for stock's sector.
    """

    try:
        ensure_yfinance_cache()

        sector = get_stock_sector(
            stock_symbol
        )

        if not sector:

            return pd.DataFrame()

        sector_symbol = get_sector_symbol(
            sector
        )

        if not sector_symbol:

            return pd.DataFrame()

        df = yf.download(
            sector_symbol,
            period=period,
            interval=interval,
            progress=False,
            session=get_yfinance_session()
        )

        return df

    except Exception as e:

        logger.error(
            f"Sector data failed: {e}"
        )

        return pd.DataFrame()
