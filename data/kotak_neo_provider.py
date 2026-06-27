from __future__ import annotations

import os
from datetime import datetime
from typing import Any
import pyotp
from neo_api_client import NeoAPI

from data.market_data_provider import MarketDataProvider, YahooFinanceProvider
from utils.logger import logger

class KotakNeoProvider(MarketDataProvider):
    def __init__(self) -> None:
        self.yf_provider = YahooFinanceProvider()
        self.client = None
        self._symbol_to_token_cache: dict[str, tuple[str, str]] = {} # symbol -> (token, segment)
        self.authenticated = False
        self._init_client()

    def _init_client(self) -> None:
        from ui.storage import load_settings
        try:
            settings = load_settings()
        except Exception:
            settings = {}

        consumer_key = os.getenv("KOTAK_CONSUMER_KEY") or settings.get("kotak_consumer_key")
        consumer_secret = os.getenv("KOTAK_CONSUMER_SECRET") or settings.get("kotak_consumer_secret")
        ucc = os.getenv("KOTAK_UCC") or settings.get("kotak_ucc")
        mpin = os.getenv("KOTAK_MPIN") or settings.get("kotak_mpin")
        totp_secret = os.getenv("KOTAK_TOTP_SECRET") or settings.get("kotak_totp_secret")
        mobile_number = os.getenv("KOTAK_MOBILE_NUMBER") or settings.get("kotak_mobile_number", "")

        # Bypass login if dummy or incomplete credentials are set
        if not consumer_key or consumer_key == "dummy_key" or not ucc or ucc == "dummy_ucc":
            logger.warning("Kotak Neo credentials are not configured or are set to dummy values. Running in fallback mode.")
            return

        try:
            logger.info("Initializing Kotak Neo API client...")
            self.client = NeoAPI(environment='prod', consumer_key=consumer_key)
            
            totp = ""
            if totp_secret and totp_secret != "dummy_totp_secret":
                totp = pyotp.TOTP(totp_secret.replace(" ", "")).now()
                
            logger.info(f"Logging in to Kotak Neo with UCC: {ucc}")
            self.client.totp_login(
                mobile_number=mobile_number,
                ucc=ucc,
                totp=totp
            )
            
            logger.info("Validating Kotak Neo session with MPIN...")
            self.client.totp_validate(mpin=mpin)
            self.authenticated = True
            logger.info("Kotak Neo API authenticated successfully.")
        except Exception as e:
            logger.error(f"Failed to authenticate Kotak Neo API: {e}. Kotak-only mode will leave quotes unavailable until credentials/session recover.")
            self.client = None
            self.authenticated = False

    def _resolve_symbol_token(self, symbol: str) -> tuple[str, str] | None:
        """
        Resolves a clean symbol to Kotak Neo (token, exchange_segment).
        """
        # Skip indices
        if symbol.startswith("^"):
            return None

        # Clean symbol
        symbol_clean = symbol.split(".")[0].upper()
        if symbol_clean in self._symbol_to_token_cache:
            return self._symbol_to_token_cache[symbol_clean]

        if not self.authenticated or not self.client:
            return None

        for segment in ["nse_cm", "bse_cm"]:
            try:
                res = self.client.search_scrip(exchange_segment=segment, symbol=symbol_clean)
                if isinstance(res, list) and len(res) > 0:
                    first = res[0]
                    token = first.get("pSymbol") or first.get("instrument_token") or first.get("exchange_instrument_id")
                    if token:
                        self._symbol_to_token_cache[symbol_clean] = (str(token), segment)
                        return str(token), segment
                elif isinstance(res, dict) and "Error Message" not in res:
                    # Some versions might return a dict format or list inside dict
                    quotes = res.get("quotes", [])
                    if isinstance(quotes, list) and len(quotes) > 0:
                        first = quotes[0]
                        token = first.get("pSymbol") or first.get("instrument_token") or first.get("exchange_instrument_id")
                        if token:
                            self._symbol_to_token_cache[symbol_clean] = (str(token), segment)
                            return str(token), segment
            except Exception as e:
                logger.debug(f"Search scrip failed for {symbol_clean} in {segment}: {e}")
                continue
        return None

    def get_indices(self) -> list[dict[str, Any]]:
        return self.yf_provider.get_indices()

    def get_quote(self, symbol: str, use_cache: bool = True, ttl: int | None = None) -> dict[str, Any]:
        # Clean the symbol from suffix if passed
        symbol_clean = symbol.split(".")[0].upper()
        if symbol.startswith("^"):
            symbol_clean = symbol

        # Try to resolve token
        resolved = self._resolve_symbol_token(symbol_clean)
        if resolved and self.client:
            token, segment = resolved
            try:
                # Query LTP quote
                res = self.client.quotes(
                    instrument_tokens=[{"instrument_token": token, "exchange_segment": segment}],
                    quote_type="ltp"
                )
                
                # Extract quote details from response
                quote_data = None
                if isinstance(res, dict):
                    quote_data = res.get("quotes", [res])[0] if res.get("quotes") else res
                elif isinstance(res, list) and len(res) > 0:
                    quote_data = res[0]

                if quote_data:
                    ltp = quote_data.get("ltp") or quote_data.get("last_price")
                    if ltp is not None:
                        ltp_val = float(ltp)
                        # Build a normalized quote dictionary
                        return {
                            "symbol": symbol_clean,
                            "current_price": ltp_val,
                            "open": float(quote_data.get("open", ltp_val)),
                            "previous_close": float(quote_data.get("close", ltp_val)),
                            "day_high": float(quote_data.get("high", ltp_val)),
                            "day_low": float(quote_data.get("low", ltp_val)),
                            "volume": float(quote_data.get("volume", 0)),
                            "provider": "kotak",
                            "source": "kotak",
                            "updated_at": datetime.now().isoformat(timespec="seconds")
                        }
            except Exception as e:
                logger.warning(f"Failed to fetch Kotak Neo quote for {symbol_clean}: {e}")

        return {}

    def get_quotes_bulk(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """
        Fetches quotes in bulk for faster bootstrapping.
        """
        results = {}
        tokens_to_query = []
        symbol_by_token = {}

        for sym in symbols:
            # Clean symbol
            sym_clean = sym.split(".")[0].upper()
            if sym.startswith("^"):
                sym_clean = sym

            resolved = self._resolve_symbol_token(sym_clean)
            if resolved:
                token, segment = resolved
                tokens_to_query.append({"instrument_token": token, "exchange_segment": segment})
                symbol_by_token[token] = sym_clean

        if tokens_to_query and self.client:
            try:
                res = self.client.quotes(instrument_tokens=tokens_to_query, quote_type="ltp")
                quotes_list = []
                if isinstance(res, dict):
                    quotes_list = res.get("quotes") or [res]
                elif isinstance(res, list):
                    quotes_list = res

                for q in quotes_list:
                    token = q.get("pSymbol") or q.get("instrument_token") or q.get("exchange_instrument_id")
                    sym = symbol_by_token.get(str(token))
                    if sym:
                        ltp = q.get("ltp") or q.get("last_price")
                        if ltp is not None:
                            ltp_val = float(ltp)
                            results[sym] = {
                                "symbol": sym,
                                "current_price": ltp_val,
                                "open": float(q.get("open", ltp_val)),
                                "previous_close": float(q.get("close", ltp_val)),
                                "day_high": float(q.get("high", ltp_val)),
                                "day_low": float(q.get("low", ltp_val)),
                                "volume": float(q.get("volume", 0)),
                                "provider": "kotak",
                                "source": "kotak",
                                "updated_at": datetime.now().isoformat(timespec="seconds")
                            }
            except Exception as e:
                logger.warning(f"Bulk Kotak Neo quote fetch failed: {e}. Falling back to individual fetches.")

        # Fill in any missing quotes using individual Kotak calls only.
        for sym in symbols:
            sym_clean = sym.split(".")[0].upper()
            if sym.startswith("^"):
                sym_clean = sym
            if sym_clean not in results:
                results[sym_clean] = self.get_quote(sym_clean)

        return results

    def get_historical_prices(self, symbol: str, period: str = "6mo", interval: str = "1d") -> list[dict[str, Any]]:
        return []

    def get_intraday_prices(self, symbol: str, interval: str = "5m") -> list[dict[str, Any]]:
        return []

    def get_financial_metrics(self, symbol: str) -> dict[str, Any]:
        return {}

    def get_news(self, symbol: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        return self.yf_provider.get_news(symbol, limit)

    def place_order(self, symbol: str, transaction_type: str, quantity: int, order_type: str = "LIMIT", price: float | None = None, **kwargs) -> dict[str, Any]:
        """
        Placeholder method for order placement. Offline/simulation only.
        """
        logger.info(f"[Offline Broker Placeholder] place_order called: symbol={symbol}, action={transaction_type}, qty={quantity}, type={order_type}, price={price}, kwargs={kwargs}")
        return {
            "status": "success",
            "order_id": f"MOCK_KOTAK_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "message": "Order simulation executed successfully (offline placeholder)",
        }

    def modify_order(self, order_id: str, quantity: int | None = None, price: float | None = None, **kwargs) -> dict[str, Any]:
        """
        Placeholder method for order modification. Offline/simulation only.
        """
        logger.info(f"[Offline Broker Placeholder] modify_order called: order_id={order_id}, qty={quantity}, price={price}, kwargs={kwargs}")
        return {
            "status": "success",
            "order_id": order_id,
            "message": "Order modification simulation executed successfully (offline placeholder)",
        }

    def cancel_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        """
        Placeholder method for order cancellation. Offline/simulation only.
        """
        logger.info(f"[Offline Broker Placeholder] cancel_order called: order_id={order_id}, kwargs={kwargs}")
        return {
            "status": "success",
            "order_id": order_id,
            "message": "Order cancellation simulation executed successfully (offline placeholder)",
        }

    def place_gtt(self, symbol: str, transaction_type: str, quantity: int, trigger_price: float, limit_price: float | None = None, **kwargs) -> dict[str, Any]:
        """
        Placeholder method for placing a GTT (Good Till Triggered) order. Offline/simulation only.
        """
        logger.info(f"[Offline Broker Placeholder] place_gtt called: symbol={symbol}, action={transaction_type}, qty={quantity}, trigger_price={trigger_price}, limit_price={limit_price}, kwargs={kwargs}")
        return {
            "status": "success",
            "gtt_id": f"MOCK_GTT_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "message": "GTT simulation executed successfully (offline placeholder)",
        }
