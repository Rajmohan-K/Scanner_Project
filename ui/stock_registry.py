from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logger import logger
from ui.stock_data_service import exchange_from_symbol, humanize_symbol, normalize_stock_symbol, symbol_base

DATA_DIR = Path(__file__).resolve().parent / "data"
REGISTRY_PATH = DATA_DIR / "stock_registry_data.json"
HISTORY_PATH = DATA_DIR / "suggestion_history.json"


class StockRegistry:
    def __init__(self) -> None:
        # Groww background tracking caches
        self.groww_all_stocks: dict[str, dict[str, Any]] = {}
        self.groww_active_intraday_stocks: set[str] = set()
        self.groww_added_stocks: set[str] = set()
        self.groww_removed_stocks: set[str] = set()

        # Custom watchlist symbols manually added
        self.custom_symbols: set[str] = set()

        # Suggestions tracking dict: symbol -> suggestion details
        self.active_suggestions: dict[str, dict[str, Any]] = {}
        self.suggestion_history: list[dict[str, Any]] = []

        self._lock = asyncio.Lock()
        self.load()

        # In-memory registry lookup cache
        self.registry_by_isin: dict[str, dict[str, Any]] = {}
        self.registry_by_nse: dict[str, dict[str, Any]] = {}
        self.registry_by_bse: dict[str, dict[str, Any]] = {}
        self.registry_by_name: dict[str, dict[str, Any]] = {}
        self.registry_by_alias: dict[str, dict[str, Any]] = {}
        self.all_companies: list[dict[str, Any]] = []
        self.autocomplete_index: list[dict[str, Any]] = []
        self._registry_loaded = False

    def load(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Load registry data
        data = {}
        if REGISTRY_PATH.exists():
            try:
                data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
                self.custom_symbols = set(data.get("custom_symbols", []))
                
                # Re-hydrate Groww caches if saved
                groww_data = data.get("groww_all_stocks", {})
                self.groww_all_stocks = {k: dict(v) for k, v in groww_data.items()}
                self.groww_active_intraday_stocks = set(data.get("groww_active_intraday_stocks", []))
                self.groww_added_stocks = set(data.get("groww_added_stocks", []))
                self.groww_removed_stocks = set(data.get("groww_removed_stocks", []))
            except Exception as e:
                logger.error(f"Failed to load stock registry data: {e}", exc_info=True)

        # Load from SignalManager
        from ui.signal_manager import signal_manager
        self.active_suggestions = signal_manager.get_active_signals()
        self.suggestion_history = signal_manager.get_signal_history()
        
        # If SQLite has no signals, but JSON has active suggestions, perform one-time migration
        if not self.active_suggestions and not self.suggestion_history and data.get("active_suggestions"):
            logger.info("StockRegistry: Migrating active suggestions from JSON to PostgreSQL database...")
            for sym, sugg in data.get("active_suggestions", {}).items():
                signal_manager.create_signal(
                    symbol=sym,
                    direction=sugg.get("direction", "BUY"),
                    entry_price=sugg.get("entry_price", sugg.get("suggested_price", 0.0)),
                    reason=sugg.get("initial_reason") or sugg.get("reason") or "",
                    target_1=sugg.get("target_1", 0.0),
                    target_2=sugg.get("target_2", 0.0),
                    stop_loss=sugg.get("stop_loss", 0.0),
                    target_3=sugg.get("target_3"),
                    initial_confidence=sugg.get("initial_confidence", 80.0),
                    provider=sugg.get("provider", "yfinance"),
                    action_at_suggestion=sugg.get("action_at_suggestion") or sugg.get("direction", "BUY")
                )
            self.active_suggestions = signal_manager.get_active_signals()
            self.suggestion_history = signal_manager.get_signal_history()
            logger.info(f"StockRegistry: Migration complete. Loaded {len(self.active_suggestions)} active suggestions.")

    def load_registry_cache(self, force: bool = False) -> None:
        if self._registry_loaded and not force:
            return
        try:
            from ui.v20_store import connect, ensure_v30_schema
            ensure_v30_schema()
            with connect() as conn:
                table_exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='company_symbol_registry'"
                ).fetchone()
                rows = []
                if table_exists:
                    rows = conn.execute("SELECT * FROM company_symbol_registry").fetchall()
            
            # Clear existing cache
            self.registry_by_isin.clear()
            self.registry_by_nse.clear()
            self.registry_by_bse.clear()
            self.registry_by_name.clear()
            self.registry_by_alias.clear()
            self.all_companies.clear()
            self.autocomplete_index.clear()

            for row in rows:
                record = _registry_row_to_dict(row, "database_cache", 1.0)
                self._add_registry_record(record)

            self._load_symbol_file_fallbacks()
            self.build_autocomplete_index()
            self._registry_loaded = True
            logger.info(f"Loaded {len(self.all_companies)} stocks into in-memory symbol resolution cache.")
        except Exception as e:
            logger.error(f"Failed to load registry cache: {e}")

    def _add_registry_record(self, record: dict[str, Any]) -> None:
        isin = str(record.get("isin") or "").upper()
        if not isin:
            return
        if isin.startswith("SYN_"):
            return
        if isin in self.registry_by_isin:
            return

        self.registry_by_isin[isin] = record

        if record.get("nse_symbol"):
            self.registry_by_nse[str(record["nse_symbol"]).upper()] = record
        if record.get("nse_ticker"):
            self.registry_by_nse[str(record["nse_ticker"]).upper()] = record

        if record.get("bse_symbol"):
            self.registry_by_bse[str(record["bse_symbol"]).upper()] = record
        if record.get("bse_ticker"):
            self.registry_by_bse[str(record["bse_ticker"]).upper()] = record

        if record.get("company_name"):
            self.registry_by_name[str(record["company_name"]).upper()] = record

        for alias in record.get("aliases", []):
            if alias:
                self.registry_by_alias[str(alias).upper()] = record

        self.all_companies.append(record)

    def _load_symbol_file_fallbacks(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        inverse_static = {ticker.upper(): name.title() for name, ticker in STATIC_NAME_MAPPINGS.items()}
        seen = {str(row.get("isin") or "").upper() for row in self.all_companies}

        for record in self._symbol_file_records(project_root, inverse_static):
            raw = str(record.get("isin") or "").upper()
            if raw and raw not in seen:
                self._add_registry_record(record)
                seen.add(raw)

    def _symbol_file_records(self, project_root: Path | None = None, inverse_static: dict[str, str] | None = None) -> list[dict[str, Any]]:
        root = project_root or Path(__file__).resolve().parent.parent
        static_names = inverse_static or {ticker.upper(): name.title() for name, ticker in STATIC_NAME_MAPPINGS.items()}
        records: list[dict[str, Any]] = []
        seen: set[str] = set()

        for path in (root / "all_symbols.txt", root / "ui" / "all_symbols.txt"):
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                raw = str(line or "").strip().upper()
                if not raw or raw in seen:
                    continue
                if not (raw.startswith("^") or raw.endswith(".NS") or raw.endswith(".BO")):
                    continue
                base = symbol_base(raw)
                if not base:
                    continue

                exchange = exchange_from_symbol(raw)
                nse_symbol = base if exchange == "NSE" else None
                bse_symbol = base if exchange == "BSE" else None
                nse_ticker = f"{base}.NS" if exchange == "NSE" else None
                bse_ticker = f"{base}.BO" if exchange == "BSE" else None
                name = static_names.get(raw) or humanize_symbol(base)
                record = {
                    "stock_id": raw,
                    "company_name": name,
                    "isin": raw,
                    "nse_symbol": nse_symbol,
                    "bse_symbol": bse_symbol,
                    "nse_ticker": nse_ticker,
                    "bse_ticker": bse_ticker,
                    "preferred_exchange": exchange,
                    "active_quote_source": exchange,
                    "resolved_from": "symbol_file_fallback",
                    "confidence": 0.7,
                    "fallback_reason": "Loaded from bundled symbol universe",
                    "aliases": [base, raw],
                }
                records.append(record)
                seen.add(raw)
        return records

    def ensure_symbol_universe_in_db(self) -> int:
        try:
            from ui.v20_store import connect, ensure_v30_schema
            ensure_v30_schema()
            records = self._symbol_file_records()
            inserted = 0
            now_str = datetime.now().isoformat(timespec="seconds")
            with connect() as conn:
                for record in records:
                    conn.execute(
                        """
                        INSERT INTO company_symbol_registry (
                            isin, company_name, company_aliases, sector,
                            nse_symbol, bse_symbol, nse_ticker, bse_ticker,
                            preferred_exchange, active_quote_source, fallback_reason, last_verified
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(isin) DO NOTHING
                        """,
                        (
                            record["isin"],
                            record["company_name"],
                            json.dumps(record.get("aliases", [])),
                            record.get("sector") or "",
                            record.get("nse_symbol"),
                            record.get("bse_symbol"),
                            record.get("nse_ticker"),
                            record.get("bse_ticker"),
                            record.get("preferred_exchange") or "NSE",
                            record.get("active_quote_source") or "NSE",
                            record.get("fallback_reason"),
                            now_str,
                        )
                    )
                    inserted += 1
            logger.info(f"Ensured bundled symbol universe in database ({inserted} candidates).")
            return inserted
        except Exception as exc:
            logger.warning(f"Failed to ensure bundled symbol universe in database: {exc}")
            return 0

    def build_autocomplete_index(self) -> None:
        index: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in self.all_companies:
            symbol = record.get("nse_ticker") or record.get("bse_ticker") or record.get("nse_symbol") or record.get("bse_symbol") or record.get("isin")
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            tokens = [
                record.get("company_name"),
                record.get("isin"),
                record.get("nse_symbol"),
                record.get("bse_symbol"),
                record.get("nse_ticker"),
                record.get("bse_ticker"),
                record.get("sector"),
                *(record.get("aliases") or []),
            ]
            searchable = " ".join(str(token).upper() for token in tokens if token)
            index.append(
                {
                    "searchable": searchable,
                    "symbol": symbol,
                    "isin": record.get("isin"),
                    "nse_symbol": record.get("nse_symbol"),
                    "bse_symbol": record.get("bse_symbol"),
                    "nse_ticker": record.get("nse_ticker"),
                    "bse_ticker": record.get("bse_ticker"),
                    "exchange": record.get("preferred_exchange") or "NSE",
                    "name": record.get("company_name"),
                    "preferred_exchange": record.get("preferred_exchange") or "NSE",
                    "active_quote_source": record.get("active_quote_source") or "NSE",
                    "sector": record.get("sector"),
                }
            )
        self.autocomplete_index = index

    def suggest(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        self.load_registry_cache()
        needle = str(query or "").strip().upper()
        if not needle:
            return []
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in self.autocomplete_index:
            text = item["searchable"]
            symbol = str(item.get("symbol") or "").upper()
            nse = str(item.get("nse_symbol") or "").upper()
            name = str(item.get("name") or "").upper()
            if needle not in text:
                continue
            if symbol.startswith(needle) or nse.startswith(needle):
                score = 0
            elif name.startswith(needle):
                score = 1
            else:
                score = 2
            scored.append((score, item))
        scored.sort(key=lambda row: (row[0], str(row[1].get("symbol") or "")))
        return [{k: v for k, v in item.items() if k != "searchable"} for _, item in scored[:limit]]

    def persist(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "custom_symbols": list(self.custom_symbols),
                "active_suggestions": self.active_suggestions,
                "groww_all_stocks": self.groww_all_stocks,
                "groww_active_intraday_stocks": list(self.groww_active_intraday_stocks),
                "groww_added_stocks": list(self.groww_added_stocks),
                "groww_removed_stocks": list(self.groww_removed_stocks),
            }
            REGISTRY_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to persist stock registry: {e}", exc_info=True)

    def persist_history(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            # Limit history to last 1000 items
            HISTORY_PATH.write_text(json.dumps(self.suggestion_history[-1000:], indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to persist suggestion history: {e}", exc_info=True)

    async def update_groww_stocks(self, current_groww_list: list[dict[str, Any]]) -> None:
        """
        Updates the internal cache of Groww stocks. Performs incremental syncing.
        """
        async with self._lock:
            now_str = datetime.now().isoformat(timespec="seconds")
            current_symbols = {normalize_stock_symbol(item["symbol"]) for item in current_groww_list if item.get("symbol")}
            current_symbols.discard("")

            # 1. Identify newly added stocks
            newly_added = current_symbols - set(self.groww_all_stocks.keys())
            for sym in newly_added:
                # Find matching row details
                row_detail = next((item for item in current_groww_list if normalize_stock_symbol(item.get("symbol")) == sym), {})
                self.groww_all_stocks[sym] = {
                    "symbol": sym,
                    "company": row_detail.get("company") or row_detail.get("name") or sym,
                    "first_seen_at": now_str,
                    "last_seen_at": now_str,
                    "last_updated_at": now_str,
                    "active_status": "active",
                }
                self.groww_added_stocks.add(sym)
                self.groww_removed_stocks.discard(sym)

            # 2. Identify removed stocks
            removed_symbols = set(self.groww_all_stocks.keys()) - current_symbols
            for sym in removed_symbols:
                if self.groww_all_stocks[sym]["active_status"] == "active":
                    self.groww_all_stocks[sym]["active_status"] = "removed"
                    self.groww_all_stocks[sym]["last_updated_at"] = now_str
                    self.groww_removed_stocks.add(sym)
                    self.groww_added_stocks.discard(sym)

            # 3. Update last seen and details of existing active stocks
            for item in current_groww_list:
                sym = normalize_stock_symbol(item.get("symbol"))
                if not sym or sym not in current_symbols:
                    continue
                if sym in self.groww_all_stocks:
                    self.groww_all_stocks[sym]["last_seen_at"] = now_str
                    self.groww_all_stocks[sym]["active_status"] = "active"
                    # Update price/volume details if passed
                    for key in ["current_price", "price_change_pct", "volume_spike", "change_pct", "volume"]:
                        if key in item:
                            self.groww_all_stocks[sym][key] = item[key]

            # Update active intraday set
            self.groww_active_intraday_stocks = current_symbols
            self.persist()

            # Ensure active Groww symbols are tracked by stock_data_service
            try:
                from ui.stock_data_service import stock_data_service
                for sym in current_symbols:
                    stock_data_service.tracked_symbols.add(sym)
            except Exception as e:
                logger.error(f"Failed to push Groww symbols to tracked_symbols: {e}")

    async def add_custom_symbol(self, symbol: str) -> None:
        async with self._lock:
            normalized = normalize_stock_symbol(symbol)
            if normalized:
                self.custom_symbols.add(normalized)
                self.persist()

    async def remove_custom_symbol(self, symbol: str) -> None:
        async with self._lock:
            normalized = normalize_stock_symbol(symbol)
            if normalized in self.custom_symbols:
                self.custom_symbols.discard(normalized)
                self.persist()

    async def register_suggestion(
        self,
        symbol: str,
        entry_price: float,
        reason: str,
        target_1: float,
        target_2: float,
        stop_loss: float,
        direction: str = "BUY",
        target_3: float | None = None,
        initial_confidence: float = 80.0,
        provider: str = "yfinance",
    ) -> None:
        """
        Registers a new V50 Signal Record if not already active.
        """
        async with self._lock:
            from ui.signal_manager import signal_manager
            signal_manager.create_signal(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                reason=reason,
                target_1=target_1,
                target_2=target_2,
                stop_loss=stop_loss,
                target_3=target_3,
                initial_confidence=initial_confidence,
                provider=provider,
                action_at_suggestion=direction
            )
            # Sync in-memory caches
            self.active_suggestions = signal_manager.get_active_signals()
            self.suggestion_history = signal_manager.get_signal_history()
            self.persist()

    async def update_suggestion_prices(self, symbol: str, current_price: float, latest_confidence: float | None = None, latest_analysis: str | None = None, provider: str | None = None, freshness: str = "LIVE") -> None:
        """
        Continuously tracks suggestion returns, highs, lows, and hits.
        Updates every market tick without modifying the original frozen signal values.
        """
        async with self._lock:
            from ui.signal_manager import signal_manager
            signal_manager.update_signal_live_metrics(
                symbol=symbol,
                current_price=current_price,
                latest_confidence=latest_confidence,
                latest_analysis=latest_analysis,
                provider=provider,
                freshness=freshness
            )
            # Sync in-memory caches
            self.active_suggestions = signal_manager.get_active_signals()
            self.suggestion_history = signal_manager.get_signal_history()
            self.persist()

    def _archive_suggestion(self, symbol: str, sugg: dict[str, Any], exit_price: float, outcome: str) -> None:
        pass

    async def clear_suggestion(self, symbol: str) -> None:
        async with self._lock:
            from ui.signal_manager import signal_manager
            signal_manager.manual_close_signal(symbol)
            # Sync in-memory caches
            self.active_suggestions = signal_manager.get_active_signals()
            self.suggestion_history = signal_manager.get_signal_history()
            self.persist()


stock_registry = StockRegistry()


STATIC_NAME_MAPPINGS = {
    "ASM TECHNOLOGIES": "ASMTEC.BO",
    "AVANTI FEEDS": "AVANTIFEED.NS",
    "RELIANCE INDUSTRIES": "RELIANCE.NS",
    "TATA CONSULTANCY SERVICES": "TCS.NS",
    "INFOSYS": "INFY.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "SEPC LIMIT": "SEPC.NS",
    "SEPC LIMITED": "SEPC.NS",
    "INOX WIND": "INOXWIND.NS",
    "INOX WIND LIMITED": "INOXWIND.NS",
    "NETWEB TECHNOLOGIES": "NETWEB.NS",
    "MTAR TECHNOLOGIES": "MTARTECH.NS",
    "VIKRAM SOLAR": "VIKRAMSOLR.NS",
    "WAAREE ENERGIES": "WAAREEENER.NS",
    "RAIL VIKAS NIGAM": "RVNL.NS",
    "OLA ELECTRIC": "OLAELEC.NS",
}

STATIC_INDEX_MAPPINGS = {
    "^NSEI": {
        "stock_id": "^NSEI",
        "company_name": "NIFTY 50",
        "isin": "^NSEI",
        "nse_symbol": "^NSEI",
        "bse_symbol": None,
        "nse_ticker": "^NSEI",
        "bse_ticker": None,
        "preferred_exchange": "INDEX",
        "active_quote_source": "INDEX",
        "resolved_from": "static_index",
        "confidence": 1.0,
        "fallback_reason": None,
        "aliases": ["NIFTY", "NIFTY 50", "NSEI"],
    },
    "^BSESN": {
        "stock_id": "^BSESN",
        "company_name": "SENSEX",
        "isin": "^BSESN",
        "nse_symbol": None,
        "bse_symbol": "^BSESN",
        "nse_ticker": None,
        "bse_ticker": "^BSESN",
        "preferred_exchange": "INDEX",
        "active_quote_source": "INDEX",
        "resolved_from": "static_index",
        "confidence": 1.0,
        "fallback_reason": None,
        "aliases": ["SENSEX", "BSESN"],
    },
}


def _registry_row_to_dict(row: Any, resolved_from: str, confidence: float) -> dict[str, Any]:
    import json
    try:
        aliases = json.loads(row["company_aliases"]) if row["company_aliases"] else []
    except Exception:
        aliases = []
        
    return {
        "stock_id": row["isin"],
        "company_name": row["company_name"],
        "isin": row["isin"],
        "nse_symbol": row["nse_symbol"],
        "bse_symbol": row["bse_symbol"],
        "nse_ticker": row["nse_ticker"],
        "bse_ticker": row["bse_ticker"],
        "preferred_exchange": row["preferred_exchange"] or "NSE",
        "active_quote_source": row["active_quote_source"] or "NSE",
        "resolved_from": resolved_from,
        "confidence": confidence,
        "fallback_reason": row["fallback_reason"],
        "aliases": aliases
    }


def _lookup_yahoo_search(query_str: str) -> dict[str, Any] | None:
    # Reject synthetic ISINs immediately — they are not resolvable
    if query_str.upper().startswith("SYN_"):
        return None
    # Simple rate limiter: max 3 calls per 6 seconds to avoid 429
    _lookup_yahoo_search._last_calls = getattr(_lookup_yahoo_search, "_last_calls", [])
    now_ts = time.time()
    _lookup_yahoo_search._last_calls = [t for t in _lookup_yahoo_search._last_calls if now_ts - t < 6.0]
    if len(_lookup_yahoo_search._last_calls) >= 3:
        logger.debug(f"Yahoo Search rate-limited; skipping remote lookup for: {query_str}")
        return None
    _lookup_yahoo_search._last_calls.append(now_ts)
    try:
        import urllib.parse
        import json
        import yfinance as yf
        from data.yfinance_utils import get_yfinance_session
        from datetime import datetime
        
        session = get_yfinance_session()
        quoted_query = urllib.parse.quote(query_str)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={quoted_query}"
        
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        search_data = resp.json()
        quotes = search_data.get("quotes", [])
        if not quotes:
            return None
            
        target_ticker = None
        for q in quotes:
            symbol = q.get("symbol", "")
            if symbol.endswith(".NS") or symbol.endswith(".BO"):
                target_ticker = symbol
                break
                
        if not target_ticker:
            if quotes:
                target_ticker = quotes[0].get("symbol")
                
        if not target_ticker:
            return None
            
        try:
            ticker_obj = yf.Ticker(target_ticker, session=session)
            isin = ticker_obj.isin
        except Exception:
            isin = None
            
        if not isin or not isinstance(isin, str) or isin == "-":
            isin = target_ticker.upper()
            
        url_isin = f"https://query2.finance.yahoo.com/v1/finance/search?q={isin}"
        resp_isin = session.get(url_isin, timeout=10)
        resp_isin.raise_for_status()
        isin_data = resp_isin.json()
        isin_quotes = isin_data.get("quotes", [])
        
        company_name = None
        nse_ticker = None
        bse_ticker = None
        nse_symbol = None
        bse_symbol = None
        
        for q in isin_quotes:
            sym = q.get("symbol", "")
            if sym.endswith(".NS"):
                nse_ticker = sym
                nse_symbol = sym.split(".")[0]
                if not company_name:
                    company_name = q.get("longname") or q.get("shortname")
            elif sym.endswith(".BO"):
                bse_ticker = sym
                bse_symbol = sym.split(".")[0]
                if not company_name:
                    company_name = q.get("longname") or q.get("shortname")
                    
        if not company_name:
            first_q = isin_quotes[0] if isin_quotes else quotes[0]
            company_name = first_q.get("longname") or first_q.get("shortname") or target_ticker
            
        if target_ticker.endswith(".NS"):
            nse_ticker = target_ticker
            nse_symbol = target_ticker.split(".")[0]
        elif target_ticker.endswith(".BO"):
            bse_ticker = target_ticker
            bse_symbol = target_ticker.split(".")[0]
            
        if not company_name:
            company_name = query_str
            
        preferred_exchange = "NSE" if nse_ticker else "BSE"
        active_quote_source = "NSE" if nse_ticker else "BSE"
        
        return {
            "stock_id": isin,
            "company_name": company_name,
            "isin": isin,
            "nse_symbol": nse_symbol,
            "bse_symbol": bse_symbol,
            "nse_ticker": nse_ticker,
            "bse_ticker": bse_ticker,
            "preferred_exchange": preferred_exchange,
            "active_quote_source": active_quote_source,
            "resolved_from": "yahoo_search",
            "confidence": 1.0,
            "fallback_reason": None,
            "aliases": [query_str] if query_str.upper() not in (company_name.upper(), (nse_symbol or "").upper(), (bse_symbol or "").upper()) else []
        }
    except Exception as exc:
        logger.error(f"Yahoo Search Dynamic Lookup failed for query {query_str}: {exc}")
        return None


def is_indian_stock(record: dict[str, Any]) -> bool:
    if not record:
        return False
    isin = str(record.get("isin") or "").upper()
    nse = str(record.get("nse_ticker") or "").upper()
    bse = str(record.get("bse_ticker") or "").upper()
    sym = str(record.get("symbol") or record.get("nse_symbol") or record.get("bse_symbol") or "").upper()
    
    if isin.startswith("IN"):
        return True
    if isin.startswith("^"):
        return True
    if nse.endswith(".NS") or bse.endswith(".BO"):
        return True
    if sym.endswith(".NS") or sym.endswith(".BO") or sym.startswith("^"):
        return True
    if isin.startswith("SYN_") and ("_NS" in isin or "_BO" in isin or "NS" in isin or "BO" in isin):
        return True
    return False


def resolve_stock_identifier(input_str: str, allow_remote: bool = False) -> dict[str, Any] | None:
    if not input_str:
        return None
    
    q = str(input_str).strip().upper()
    if not q:
        return None

    # Synthetic ISINs (SYN_*) are placeholder values — never resolvable
    if q.startswith("SYN_"):
        return None

    # Static name to ticker override mapping
    if q in STATIC_INDEX_MAPPINGS:
        return dict(STATIC_INDEX_MAPPINGS[q])

    static_mapped = STATIC_NAME_MAPPINGS.get(q)
    if static_mapped:
        q = static_mapped.upper()

    import json
    import difflib
    from datetime import datetime

    stock_registry.load_registry_cache()

    res = None
    resolved_from = None
    confidence = 1.0

    # Priority 1: Match by ISIN in-memory
    match = stock_registry.registry_by_isin.get(q)
    if match:
        res, resolved_from = match, "isin"

    # Priority 2: Match by exact NSE symbol or ticker in-memory
    if not res:
        match = stock_registry.registry_by_nse.get(q)
        if match:
            res, resolved_from = match, "nse_symbol"

    # Priority 3: Match by exact BSE symbol or ticker in-memory
    if not res:
        match = stock_registry.registry_by_bse.get(q)
        if match:
            res, resolved_from = match, "bse_symbol"

    # Priority 4: Match by exact Company Name in-memory
    if not res:
        match = stock_registry.registry_by_name.get(q)
        if match:
            res, resolved_from = match, "company_name"

    # Priority 5: Match by exact alias in-memory
    if not res:
        match = stock_registry.registry_by_alias.get(q)
        if match:
            res, resolved_from = match, "alias"

    # Priority 6: Fuzzy company name or alias match in-memory
    if not res:
        best_match = None
        best_score = 0.0
        for r in stock_registry.all_companies:
            name = r.get("company_name", "")
            score = difflib.SequenceMatcher(None, q, name.upper()).ratio()
            if score > best_score:
                best_score = score
                best_match = r
            
            for alias in r.get("aliases", []):
                score = difflib.SequenceMatcher(None, q, str(alias).upper()).ratio()
                if score > best_score:
                    best_score = score
                    best_match = r

        if best_match and best_score >= 0.95:
            res, resolved_from, confidence = best_match, "fuzzy", round(best_score, 2)

    if res:
        resolved_data = {**res, "resolved_from": resolved_from, "confidence": confidence}
        if is_indian_stock(resolved_data):
            return resolved_data
        logger.warning(f"Registry Search: Rejecting non-Indian stock {resolved_data}")
        return None

    # Priority 7: Dynamic lookup via Yahoo Search API (only if allowed)
    if allow_remote:
        resolved_data = _lookup_yahoo_search(input_str)
        if resolved_data:
            if not is_indian_stock(resolved_data):
                logger.warning(f"Yahoo Search: Rejecting non-Indian stock {resolved_data}")
                return None
            
            from ui.v20_store import connect
            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO company_symbol_registry (
                        isin, company_name, company_aliases, sector,
                        nse_symbol, bse_symbol, nse_ticker, bse_ticker,
                        preferred_exchange, active_quote_source, fallback_reason, last_verified
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(isin) DO UPDATE SET
                        company_name=excluded.company_name,
                        company_aliases=excluded.company_aliases,
                        nse_symbol=excluded.nse_symbol,
                        bse_symbol=excluded.bse_symbol,
                        nse_ticker=excluded.nse_ticker,
                        bse_ticker=excluded.bse_ticker,
                        last_verified=excluded.last_verified
                    """,
                    (
                        resolved_data["isin"],
                        resolved_data["company_name"],
                        json.dumps(resolved_data.get("aliases", [])),
                        resolved_data.get("sector"),
                        resolved_data["nse_symbol"],
                        resolved_data["bse_symbol"],
                        resolved_data["nse_ticker"],
                        resolved_data["bse_ticker"],
                        resolved_data["preferred_exchange"],
                        resolved_data["active_quote_source"],
                        resolved_data.get("fallback_reason"),
                        datetime.now().isoformat(timespec="seconds"),
                    )
                )
            # Force cache reload to include the newly resolved stock
            stock_registry.load_registry_cache(force=True)
            return resolved_data

    return None


async def sync_company_symbol_registry() -> None:
    """
    Downloads NSE EQUITY_L list and updates company_symbol_registry daily.
    """
    import csv
    import io
    import json
    import ssl
    import urllib.request
    from datetime import datetime
    from utils.logger import logger
    from ui.v20_store import connect

    logger.info("Starting background Company Symbol Registry daily builder...")
    ssl_context = ssl._create_unverified_context()
    
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    
    nse_rows = []
    try:
        loop = asyncio.get_running_loop()
        def fetch():
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
                return response.read().decode('utf-8')
        content = await loop.run_in_executor(None, fetch)
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames if f]
        nse_rows = list(reader)
        logger.info(f"NSE Equity list downloaded successfully. Rows: {len(nse_rows)}")
    except Exception as e:
        logger.error(f"Failed to download NSE Equity list: {e}", exc_info=True)
        return

    now_str = datetime.now().isoformat(timespec="seconds")
    
    with connect() as conn:
        for row in nse_rows:
            symbol = (row.get("SYMBOL") or "").strip()
            name = (row.get("NAME OF COMPANY") or "").strip()
            isin = (row.get("ISIN NUMBER") or "").strip()
            series = (row.get("SERIES") or "").strip().upper()
            
            if not symbol or not isin or not name:
                continue
                
            if series not in ("EQ", "BE", "BZ"):
                continue
                
            aliases = [symbol]
            short_name = name
            for suffix in (" LIMITED", " LTD.", " LTD", " CORP.", " CORP", " CORPORATION"):
                if short_name.upper().endswith(suffix):
                    short_name = short_name[:-len(suffix)].strip()
            if short_name and short_name.upper() != name.upper() and short_name not in aliases:
                aliases.append(short_name)
                
            existing = conn.execute("SELECT bse_symbol, bse_ticker, company_aliases FROM company_symbol_registry WHERE isin = ?", (isin,)).fetchone()
            bse_sym = None
            bse_tick = None
            if existing:
                bse_sym = existing["bse_symbol"]
                bse_tick = existing["bse_ticker"]
                try:
                    loaded_aliases = json.loads(existing["company_aliases"])
                    for la in loaded_aliases:
                        if la not in aliases:
                            aliases.append(la)
                except Exception:
                    pass

            conn.execute(
                """
                INSERT INTO company_symbol_registry (
                    isin, company_name, company_aliases, sector,
                    nse_symbol, bse_symbol, nse_ticker, bse_ticker,
                    preferred_exchange, active_quote_source, last_verified
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(isin) DO UPDATE SET
                    company_name=excluded.company_name,
                    company_aliases=excluded.company_aliases,
                    nse_symbol=excluded.nse_symbol,
                    nse_ticker=excluded.nse_ticker,
                    last_verified=excluded.last_verified
                """,
                (
                    isin,
                    name,
                    json.dumps(aliases),
                    "",
                    symbol,
                    bse_sym,
                    f"{symbol}.NS",
                    bse_tick,
                    "NSE",
                    "NSE",
                    now_str
                )
            )
            
    logger.info("Successfully updated company_symbol_registry table with latest NSE list.")


async def resolve_missing_bse_symbols_worker() -> None:
    """
    Background worker that fetches missing BSE symbols/tickers using Yahoo Finance Search API.
    """
    from ui.v20_store import connect
    import json
    from utils.logger import logger
    
    logger.info("BSE dynamic resolution worker started.")
    
    try:
        from ui.watchlist_monitor import watchlist_monitor
        monitored_symbols = {item.get("symbol") for item in watchlist_monitor.list_items()}
    except Exception:
        monitored_symbols = set()
        
    with connect() as conn:
        records = conn.execute(
            "SELECT isin, nse_ticker, company_name FROM company_symbol_registry WHERE bse_ticker IS NULL OR bse_ticker = ''"
        ).fetchall()
        
    if not records:
        logger.info("No missing BSE symbols to resolve.")
        return
        
    records_to_process = []
    other_records = []
    
    for r in records:
        if r["nse_ticker"] in monitored_symbols or r["isin"] in monitored_symbols:
            records_to_process.append(r)
        else:
            other_records.append(r)
            
    records_to_process.extend(other_records)
    logger.info(f"Registry has {len(records_to_process)} records with missing BSE tickers. Resolving...")
    
    resolved_count = 0
    for i, r in enumerate(records_to_process):
        isin = r["isin"]
        nse_ticker = r["nse_ticker"]
        
        try:
            with connect() as conn:
                check = conn.execute("SELECT bse_ticker FROM company_symbol_registry WHERE isin = ?", (isin,)).fetchone()
                if check and check["bse_ticker"]:
                    continue
                    
            resolved = await asyncio.to_thread(_lookup_yahoo_search, isin)
            if resolved and resolved.get("bse_ticker"):
                bse_ticker = resolved["bse_ticker"]
                bse_symbol = resolved["bse_symbol"]
                
                with connect() as conn:
                    conn.execute(
                        "UPDATE company_symbol_registry SET bse_symbol = ?, bse_ticker = ? WHERE isin = ?",
                        (bse_symbol, bse_ticker, isin)
                    )
                resolved_count += 1
                logger.debug(f"Resolved BSE ticker for {nse_ticker}: {bse_ticker}")
            
            delay = 1.5 if i < len(monitored_symbols) else 3.0
            await asyncio.sleep(delay)
            
            if resolved_count >= 150:
                logger.info("Reached maximum background BSE resolutions (150) for this cycle.")
                break
        except Exception as e:
            logger.debug(f"Failed resolving BSE ticker for {isin}: {e}")
            await asyncio.sleep(5)
            
    logger.info(f"BSE resolution worker finished. Resolved {resolved_count} symbols.")
