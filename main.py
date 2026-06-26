from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*timedelta.*")

import argparse
import re
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from backtesting.walk_forward import run_walk_forward
from backtesting.strategy_tester import run_strategy_test
from backtesting.optimization_engine import optimize_strategy
from analysis import breadth_analysis
from analysis.breakout_analysis import run as breakout_analysis
from analysis.candlestick_analysis import run as candlestick_analysis
from analysis.chart_pattern_analysis import run as chart_pattern_analysis
from analysis.correlation_analysis import run as correlation_analysis
from analysis.delivery_analysis import run as delivery_analysis
from analysis.earnings_analysis import run as earnings_analysis
from analysis.event_impact_analysis import run as event_impact_analysis
from analysis.fibonacci_analysis import run as fibonacci_analysis
from analysis.fundamentals_analysis import run as fundamentals_analysis
from analysis.gap_analysis import run as gap_analysis
from analysis.insider_activity import run as insider_activity_analysis
from analysis.liquidity_analysis import run as liquidity_analysis
from analysis.market_structure import run as market_structure_analysis
from analysis.momentum_analysis import run as momentum_analysis
from analysis.options_analysis import run as options_analysis
from analysis.order_block_analysis import run as order_block_analysis
from analysis.pivot_analysis import run as pivot_analysis
from analysis.relative_strength import run as relative_strength_analysis
from analysis.seasonality_analysis import run as seasonality_analysis
from analysis.sector_strength import run as sector_strength_analysis
from analysis.smart_money_analysis import run as smart_money_analysis
from analysis.support_resistance import run as support_resistance_analysis
from analysis.technical_analysis import run as technical_analysis
from analysis.trend_analysis import run as trend_analysis
from analysis.valuation_analysis import run as valuation_analysis
from analysis.volatility_analysis import run as volatility_analysis
from analysis.volume_analysis import run as volume_analysis
from analysis.vwap_analysis import run as vwap_analysis
from analysis.market_open_validation import build_market_open_validation
from data.direct_feeds import build_event_snapshot
from data.fundamental_data import get_fundamental_data
from data.macro_data import get_advanced_macro_data, get_global_market_data
from data.market_data import get_bulk_stock_data, get_live_price, get_live_quote, get_stock_data
from data.news_data import get_market_news, get_stock_news
from data.options_data import get_options_data
from data.sector_data import get_sector_symbol, get_stock_sector
from data.universe_data import fetch_nse_universe, write_symbols_file
from ml.feature_engineering import build_feature_vector
from ml.predictor import predict_probability
from ml.probability_ranker import blend_probability
from regime.regime_detector import detect_market_regime
from reports.report_generator import generate_scan_report
from scoring.confidence_engine import calculate_confidence
from scoring.premarket_gate import evaluate_premarket_readiness
from scoring.quality_filter import annotate_deep_filter, passes_fast_filter
from scoring.ranking_engine import rank_stocks
from scoring.risk_model import calculate_risk
from scoring.score_engine import calculate_score
from sentiment.fii_dii_analysis import analyze_fii_dii
from sentiment.global_sentiment import analyze_global_sentiment
from sentiment.news_sentiment import analyze_news_sentiment
from sentiment.war_analysis import analyze_war_risk
from trading.signal_engine import generate_signal
from trading.target_engine import generate_targets
from trading.trade_engine import generate_signal as generate_trade_signal
from scanners.router import build_scan_metadata, normalize_scan_mode, scanner_profile, tag_records
from utils.helpers import normalize_value, validate_dataframe
from utils.logger import logger
from utils.telegram import send_telegram_messages

VALID_SYMBOL_RE = re.compile(r"^[A-Z0-9\.\-_]+$")
INVALID_SYMBOLS = {"UNDEFINED", "NONE", "N/A", "NA", "NULL", "UNKNOWN"}
PROJECT_ROOT = Path(__file__).resolve().parent
ALL_SYMBOLS_PATH = PROJECT_ROOT / "all_symbols.txt"


def normalize_symbol(symbol: Any) -> str | None:
    if symbol is None:
        return None
    value = str(symbol).strip().upper()
    if not value or value in INVALID_SYMBOLS or not VALID_SYMBOL_RE.match(value):
        return None
    return value


def is_valid_symbol(symbol: str) -> bool:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return False
    if normalized.startswith("^"):
        return True
    return normalized.endswith(".NS") or normalized.endswith(".BO")


def safe_print(*values: Any, **kwargs: Any) -> None:
    try:
        print(*values, **kwargs)
    except OSError as exc:
        logger.warning(f"Console output unavailable: {exc}")


WATCHLIST = []

with ALL_SYMBOLS_PATH.open("r") as f:
    WATCHLIST = [line.strip() for line in f if is_valid_symbol(line.strip())]


DEFAULT_BENCHMARK = "^NSEI"
MIN_ROWS = 60
OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-factor stock signal scanner"
    )
    parser.add_argument("--symbols", nargs="+", default=WATCHLIST)
    parser.add_argument("--period", default="6mo")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--symbols-file")
    parser.add_argument("--candidate-pool", type=int, default=150)
    parser.add_argument("--validation-pool", type=int, default=25)
    parser.add_argument("--enable-deep-validation", action="store_true", help="Run slower walk-forward and optimization validation for the selected validation pool")
    parser.add_argument("--strict-shortlist", action="store_true")
    parser.add_argument("--min-expected-return-pct", type=float, default=5.0)
    parser.add_argument("--min-ml-probability", type=float, default=None)
    parser.add_argument("--min-risk-reward", type=float, default=None)
    parser.add_argument("--max-stop-distance-pct", type=float, default=None)
    parser.add_argument("--min-data-reliability-score", type=float, default=None)
    parser.add_argument("--min-profitability-score", type=float, default=None)
    parser.add_argument("--market-open-analysis", action="store_true", help="Include post-market-open 9:08 analysis for selected stocks")
    parser.add_argument("--market-open-time", default="09:08", help="Target intraday time for market-open analysis")
    parser.add_argument("--market-open-interval", default="1m", help="Interval used for intraday market-open data")
    parser.add_argument("--notify-telegram", action="store_true", help="Send scan summary and report via Telegram after scan completes")
    parser.add_argument("--telegram-category", default="Premarket", help="Telegram category for scan notifications")
    parser.add_argument("--scan-mode", default="standard", help="Scan/report mode: intraday, swing, premarket, standard")
    parser.add_argument("--pipeline-stage", default="", help="Dedicated scanner pipeline stage")
    parser.add_argument("--auto-nse-universe", action="store_true")
    parser.add_argument("--refresh-universe", action="store_true")
    parser.add_argument("--universe-output", default="all_symbols.txt")
    return parser.parse_args()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_filter_overrides(args: argparse.Namespace) -> dict[str, Any]:
    mapping = {
        "min_expected_return_pct": getattr(args, "min_expected_return_pct", None),
        "min_ml_probability": getattr(args, "min_ml_probability", None),
        "min_risk_reward": getattr(args, "min_risk_reward", None),
        "max_stop_distance_pct": getattr(args, "max_stop_distance_pct", None),
        "min_data_reliability_score": getattr(args, "min_data_reliability_score", None),
        "min_profitability_score": getattr(args, "min_profitability_score", None),
    }
    return {key: value for key, value in mapping.items() if value is not None}


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    clean = df.copy()

    if isinstance(clean.columns, pd.MultiIndex):
        flattened = []
        canonical_names = {name.lower() for name in OHLCV_COLUMNS}
        for col in clean.columns:
            parts = [str(part) for part in col if str(part)]
            canonical = next(
                (part for part in parts if part.lower() in canonical_names),
                parts[0],
            )
            flattened.append(canonical)
        clean.columns = flattened

    rename_map: dict[str, str] = {}
    lower_columns = {str(col).lower(): col for col in clean.columns}
    for name in OHLCV_COLUMNS:
        source = lower_columns.get(name.lower())
        if source is not None:
            rename_map[source] = name

    clean = clean.rename(columns=rename_map)
    available = [col for col in OHLCV_COLUMNS if col in clean.columns]
    clean = clean[available]

    for column in available:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")

    return clean.dropna().sort_index()


def is_valid_df(df: pd.DataFrame, min_rows: int = MIN_ROWS) -> bool:
    return validate_dataframe(df, min_rows=min_rows)


def fetch_symbol_data(symbol: str, period: str, interval: str) -> pd.DataFrame:
    return normalize_ohlcv(
        get_stock_data(symbol, period=period, interval=interval)
    )


def load_symbols(args: argparse.Namespace) -> list[str]:
    raw_candidates = list(args.symbols or [])

    if args.auto_nse_universe:
        nse_symbols = fetch_nse_universe(force_refresh=args.refresh_universe) or []
        raw_candidates.extend(nse_symbols)

    if args.symbols_file:
        file_path = Path(args.symbols_file)
        if file_path.exists():
            extra_symbols = [
                line.strip()
                for line in file_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            raw_candidates.extend(extra_symbols)
        else:
            logger.warning(f"Symbols file not found: {args.symbols_file}")

    # Add watchlist symbols
    try:
        from ui.watchlist_monitor import watchlist_monitor
        raw_candidates.extend([item.get("symbol") for item in watchlist_monitor.list_items() if item.get("symbol")])
        raw_candidates.extend([item.get("isin") for item in watchlist_monitor.list_items() if item.get("isin")])
    except Exception as exc:
        logger.debug(f"Failed to import watchlist symbols into scanner universe: {exc}")

    # Add active Groww and custom symbols
    try:
        from ui.stock_registry import stock_registry
        raw_candidates.extend(list(stock_registry.groww_active_intraday_stocks))
        raw_candidates.extend(list(stock_registry.custom_symbols))
    except Exception as exc:
        logger.debug(f"Failed to import registry symbols into scanner universe: {exc}")

    # Add currently tracked service symbols
    try:
        from ui.stock_data_service import stock_data_service
        raw_candidates.extend(list(stock_data_service.tracked_symbols))
    except Exception as exc:
        logger.debug(f"Failed to import tracked service symbols into scanner universe: {exc}")

    # Resolve all raw candidates via CompanySymbolRegistry to prevent duplicate records
    from ui.stock_registry import resolve_stock_identifier
    resolved_tickers = []
    seen_isins = set()

    for candidate in raw_candidates:
        if not candidate:
            continue
        try:
            resolved = resolve_stock_identifier(candidate)
            if resolved:
                isin = resolved["isin"]
                if isin not in seen_isins:
                    seen_isins.add(isin)
                    preferred_ticker = resolved.get("nse_ticker") or resolved.get("bse_ticker") or isin
                    resolved_tickers.append(preferred_ticker)
        except Exception as e:
            logger.warning(f"Failed to resolve scanner universe candidate '{candidate}': {e}")

    # Fallback to normal flow if nothing resolved
    if not resolved_tickers:
        logger.warning("Unified universe builder resolved 0 symbols. Falling back to legacy resolution.")
        deduped = []
        seen = set()
        for symbol in raw_candidates:
            normalized = normalize_symbol(symbol)
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)
        return [s for s in deduped if is_valid_symbol(s)]

    logger.info(f"Unified Scanner Universe built with {len(resolved_tickers)} stocks (deduplicated via ISIN)")
    return resolved_tickers


def fetch_all_stock_data(
    symbols: list[str], period: str, interval: str, workers: int, should_cancel=None
) -> dict[str, pd.DataFrame]:
    stock_frames: dict[str, pd.DataFrame] = {}
    valid_symbols = [symbol for symbol in (normalize_symbol(symbol) for symbol in symbols) if symbol]

    raw_frames = get_bulk_stock_data(valid_symbols, period=period, interval=interval, should_cancel=should_cancel) or {}
    for symbol in valid_symbols:
        df = normalize_ohlcv(raw_frames.get(symbol, pd.DataFrame()))
        if is_valid_df(df):
            stock_frames[symbol] = df
        else:
            logger.warning(f"Skipping {symbol}: invalid OHLCV data")

    return stock_frames


def fetch_intraday_stock_data(
    symbols: list[str],
    period: str = "1d",
    interval: str = "1m",
    workers: int = 5,
) -> dict[str, pd.DataFrame]:
    intraday_frames: dict[str, pd.DataFrame] = {}
    valid_symbols = [normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)]

    raw_frames = get_bulk_stock_data(valid_symbols, period=period, interval=interval) or {}
    for symbol in valid_symbols:
        df = normalize_ohlcv(raw_frames.get(symbol, pd.DataFrame()))
        if df is None or df.empty:
            continue
        if len(df) >= 5:
            intraday_frames[symbol] = df
    return intraday_frames


def _find_intraday_price_at_time(df: pd.DataFrame, open_time: str) -> float | None:
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return None

    try:
        target = datetime.strptime(open_time, "%H:%M").time()
    except ValueError:
        return None

    index = df.index
    if index.tz is not None:
        index = index.tz_convert(None)

    latest_date = index[-1].date()
    same_day = df.loc[index.date == latest_date]
    if same_day.empty:
        same_day = df

    eligible = same_day.loc[same_day.index.time >= target]
    if eligible.empty:
        return None

    row = eligible.iloc[0]
    price = row.get("Close")
    if pd.isna(price):
        price = row.get("Open")
    return float(price) if price is not None and not pd.isna(price) else None


def build_market_open_analysis(
    symbol: str,
    quote_data: dict[str, Any],
    intraday_df: pd.DataFrame | None = None,
    open_time: str = "09:08",
) -> dict[str, Any]:
    previous_close = quote_data.get("previous_close")
    market_open_price = quote_data.get("open")
    current_price = quote_data.get("current_price")

    analysis: dict[str, Any] = {
        "symbol": symbol,
        "open_time": open_time,
        "market_open_price": market_open_price,
        "previous_close": previous_close,
        "current_price": current_price,
        "pre_open_change_pct": None,
        "price_at_target_time": None,
        "open_to_target_change_pct": None,
        "target_vs_previous_close_pct": None,
    }

    def pct_change(base: float | None, current: float | None) -> float | None:
        if base is None or current is None or base == 0:
            return None
        return round(((current - base) / base) * 100, 2)

    if isinstance(previous_close, (int, float)) and isinstance(market_open_price, (int, float)):
        analysis["pre_open_change_pct"] = pct_change(previous_close, market_open_price)

    target_price = None
    if intraday_df is not None and not intraday_df.empty:
        target_price = _find_intraday_price_at_time(intraday_df, open_time)

    if target_price is None and isinstance(current_price, (int, float)):
        target_price = float(current_price)

    if isinstance(target_price, (int, float)):
        analysis["price_at_target_time"] = round(float(target_price), 2)
        if isinstance(market_open_price, (int, float)):
            analysis["open_to_target_change_pct"] = pct_change(market_open_price, target_price)
        if isinstance(previous_close, (int, float)):
            analysis["target_vs_previous_close_pct"] = pct_change(previous_close, target_price)

    return analysis


def calculate_market_open_analysis(
    symbols: list[str],
    open_time: str = "09:08",
    interval: str = "1m",
    workers: int = 5,
) -> dict[str, Any]:
    symbols = [normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)]
    if not symbols:
        return {}

    intraday_frames = fetch_intraday_stock_data(
        symbols,
        period="1d",
        interval=interval,
        workers=workers,
    )

    analysis_results: dict[str, Any] = {}
    for symbol in symbols:
        quote_data = get_live_quote(symbol) or {}
        intraday_df = intraday_frames.get(symbol)
        base_analysis = build_market_open_analysis(
            symbol=symbol,
            quote_data=quote_data,
            intraday_df=intraday_df,
            open_time=open_time,
        )
        validation = build_market_open_validation(
            symbol=symbol,
            quote_data=quote_data,
            intraday_df=intraday_df,
            open_time=open_time,
        )
        analysis_results[symbol] = {
            **base_analysis,
            "market_open_validation": validation,
        }
    return analysis_results


def dispatch_scan_telegram(
    scan_output: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    if not getattr(args, "notify_telegram", False):
        return

    category = getattr(args, "telegram_category", "Premarket")
    finished = scan_output.get("status") == "ok"
    symbols_scanned = scan_output.get("symbols_scanned", 0)
    candidate_count = scan_output.get("candidates_considered", 0)
    qualified = len(scan_output.get("ranked", [])) if scan_output.get("ranked") is not None else 0
    report_path = scan_output.get("report_path")

    message_lines = [
        f"Stock scanner completed: {scan_output.get('status', 'unknown').upper()}",
        f"Symbols scanned: {symbols_scanned}",
        f"Candidates considered: {candidate_count}",
        f"Qualified stocks: {qualified}",
        f"Period: {args.period} | Interval: {args.interval}",
        f"Market open analysis: {getattr(args, 'market_open_analysis', False)}",
    ]

    if report_path:
        message_lines.append(f"Report: {report_path}")

    if not finished:
        message_lines.append(f"Message: {scan_output.get('message', 'Scan did not complete successfully')}")

    ranked_rows: list[dict[str, Any]] = []
    ranked_payload = scan_output.get("ranked")
    if hasattr(ranked_payload, "to_dict"):
        ranked_rows = ranked_payload.head(10).to_dict(orient="records")
    elif isinstance(ranked_payload, list):
        ranked_rows = ranked_payload[:10]
    if not ranked_rows:
        ranked_rows = list(scan_output.get("top_25") or scan_output.get("filtered_150") or scan_output.get("results") or [])[:10]

    if ranked_rows:
        message_lines.append("")
        message_lines.append("Top trade levels:")
        for row in ranked_rows[:10]:
            symbol = row.get("stock") or row.get("symbol") or "UNKNOWN"
            live = row.get("live_price") or row.get("current_price") or row.get("last_close") or "-"
            entry = row.get("entry_price") or row.get("entry") or "-"
            stop = row.get("stop_loss") or row.get("stoploss") or "-"
            target1 = row.get("target1") or row.get("target_1") or "-"
            target2 = row.get("target2") or row.get("target_2") or "-"
            action = row.get("premarket_action") or row.get("trade_type") or row.get("action") or row.get("signal") or "WATCH"
            message_lines.append(
                f"{symbol} | {action} | LTP {live} | Entry {entry} | SL {stop} | T1 {target1} | T2 {target2}"
            )

    try:
        send_telegram_messages(category, "\n".join(message_lines), file_path=report_path)
    except Exception as exc:
        logger.error(f"Telegram dispatch failed: {exc}")


def build_breadth_payload(stock_frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    valid_frames = [df for df in stock_frames.values() if is_valid_df(df, 20)]
    total = len(valid_frames)
    if total == 0:
        return {}

    advancers = 0
    decliners = 0
    new_highs = 0
    new_lows = 0
    above_ema20 = 0
    above_ema50 = 0
    above_ema200 = 0

    for df in valid_frames:
        latest = df["Close"].iloc[-1]
        previous = df["Close"].iloc[-2]

        if latest > previous:
            advancers += 1
        elif latest < previous:
            decliners += 1

        rolling_high = df["High"].iloc[-21:-1].max() if len(df) >= 21 else df["High"].max()
        rolling_low = df["Low"].iloc[-21:-1].min() if len(df) >= 21 else df["Low"].min()
        if latest >= rolling_high:
            new_highs += 1
        if latest <= rolling_low:
            new_lows += 1

        ema20 = df["Close"].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
        ema200 = df["Close"].ewm(span=200, adjust=False).mean().iloc[-1]

        if latest > ema20:
            above_ema20 += 1
        if latest > ema50:
            above_ema50 += 1
        if latest > ema200:
            above_ema200 += 1

    return {
        "advancers": advancers,
        "decliners": decliners,
        "new_highs": new_highs,
        "new_lows": new_lows,
        "stocks_above_ema20": above_ema20,
        "stocks_above_ema50": above_ema50,
        "stocks_above_ema200": above_ema200,
        "total_stocks": total,
    }


def fetch_sector_frames(
    symbols: list[str],
    period: str,
    interval: str,
) -> dict[str, pd.DataFrame]:
    sector_frames: dict[str, pd.DataFrame] = {}
    sector_symbols = {
        sector_symbol
        for symbol in symbols
        for sector_symbol in [get_sector_symbol(get_stock_sector(symbol))]
        if sector_symbol
    }

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(fetch_symbol_data, sector_symbol, period, interval): sector_symbol
            for sector_symbol in sector_symbols
        }
        for future in as_completed(futures):
            sector_symbol = futures[future]
            try:
                sector_df = future.result()
                if is_valid_df(sector_df, 20):
                    sector_frames[sector_symbol] = sector_df
            except Exception as e:
                logger.error(f"Error fetching sector data for {sector_symbol}: {e}", exc_info=True)

    return sector_frames


def build_delivery_data(
    df: pd.DataFrame,
    event_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    direct_delivery = (event_snapshot or {}).get("delivery_data") or {}
    if direct_delivery.get("data_quality") == "real":
        latest_volume = float(df["Volume"].iloc[-1])
        delivery_percent = float(direct_delivery.get("delivery_percent", 0) or 0)
        current_delivery = float(direct_delivery.get("current_delivery_qty", 0) or 0)
        if current_delivery <= 0 and delivery_percent > 0:
            current_delivery = latest_volume * (delivery_percent / 100)
        return {
            **direct_delivery,
            "current_delivery_qty": current_delivery,
            "avg_delivery_qty": max(current_delivery, 1),
        }

    latest_volume = float(df["Volume"].iloc[-1])
    avg_volume = float(df["Volume"].tail(20).mean())
    delivery_share = 0.58 if df["Close"].iloc[-1] >= df["Close"].iloc[-2] else 0.44
    return {
        "current_delivery_qty": latest_volume * delivery_share,
        "avg_delivery_qty": avg_volume * 0.42,
        "source": "price_volume_proxy",
        "data_quality": "proxy",
    }


def build_fundamentals(symbol: str, df: pd.DataFrame) -> dict[str, Any]:
    real_fundamentals = get_fundamental_data(symbol)
    if real_fundamentals.get("data_quality") in {"real", "partial"}:
        return real_fundamentals

    close = df["Close"]
    six_month_return = ((close.iloc[-1] / close.iloc[0]) - 1) * 100
    monthly_return = ((close.iloc[-1] / close.iloc[-21]) - 1) * 100
    sector = get_stock_sector(symbol)
    debt_base = {
        "BANKING": 1.5,
        "ENERGY": 0.7,
        "IT": 0.2,
    }.get(sector, 0.5)

    return {
        "revenue_growth": clamp(8 + (six_month_return / 4), -5, 25),
        "profit_growth": clamp(6 + (monthly_return / 2), -10, 22),
        "eps_growth": clamp(5 + (monthly_return / 2.2), -10, 20),
        "roe": clamp(12 + (six_month_return / 8), 6, 24),
        "roce": clamp(11 + (six_month_return / 9), 6, 24),
        "debt_to_equity": debt_base,
        "current_ratio": 1.7 if sector != "BANKING" else 1.2,
        "pe_ratio": clamp(18 + (monthly_return / 3), 10, 40),
        "pb_ratio": clamp(2.5 + (monthly_return / 20), 1, 6),
        "promoter_holding": 52,
        "source": "price_sector_proxy",
        "data_quality": "proxy",
    }


def build_earnings_data(
    df: pd.DataFrame,
    event_snapshot: dict[str, Any] | None = None,
) -> dict[str, float | str]:
    quarter_return = ((df["Close"].iloc[-1] / df["Close"].iloc[-63]) - 1) * 100
    direct_earnings_date = (event_snapshot or {}).get("next_earnings_date", "")
    earnings_date = direct_earnings_date or (datetime.today() + timedelta(days=18)).strftime("%Y-%m-%d")
    days_to_earnings = (event_snapshot or {}).get("days_to_earnings")
    surprise_anchor = clamp(quarter_return / 3, -8, 15)
    if isinstance(days_to_earnings, int) and 0 <= days_to_earnings <= 5:
        surprise_anchor = clamp(surprise_anchor - 2, -10, 15)
    return {
        "earnings_date": earnings_date,
        "current_eps": clamp(12 + (quarter_return / 5), 5, 25),
        "previous_eps": 10,
        "current_revenue": clamp(125 + quarter_return, 85, 180),
        "previous_revenue": 110,
        "avg_surprise_percent": surprise_anchor,
    }


def merge_news_items(*groups: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or []:
            key = str(item)
            if isinstance(item, dict):
                key = f"{item.get('title', '')}|{item.get('published_at', '')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def build_fallback_ranked_candidates(
    analyzed_results: list[dict[str, Any]],
    top_n: int,
    scan_mode: str = "",
) -> pd.DataFrame:
    """Rank analyzed rows when strict quality gates remove every candidate.

    This keeps reports useful for intraday/custom scans: failed gates are
    preserved in quality_filter_reasons, but the best analyzed rows still flow
    to Excel/UI as WATCH/AVOID candidates instead of returning an empty report.
    """
    if not analyzed_results:
        return pd.DataFrame()

    df = pd.DataFrame(analyzed_results)
    if df.empty:
        return pd.DataFrame()

    numeric_defaults = {
        "score": 0,
        "confidence_pct": 0,
        "ml_probability": 0,
        "profitability_score": 0,
        "quality_score": 0,
        "technical_score": 0,
        "premarket_grade": 0,
        "expected_return": 0,
        "risk_reward": 0,
        "rrr": 0,
        "data_reliability_score": 0,
        "profit_factor": 0,
        "backtest_win_rate": 0,
        "stop_distance_pct": 0,
        "risk_score": 0,
        "max_drawdown": 0,
    }
    for column, default in numeric_defaults.items():
        if column not in df.columns:
            df[column] = default
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(default)

    if "risk_reward" in df.columns and "rrr" in df.columns:
        df["risk_reward_effective"] = df["risk_reward"].where(df["risk_reward"] > 0, df["rrr"])
    else:
        df["risk_reward_effective"] = 0

    if "trade_type" not in df.columns:
        df["trade_type"] = ""
    if "action" not in df.columns:
        df["action"] = ""
    if "quality_filter_reasons" not in df.columns:
        df["quality_filter_reasons"] = "Did not meet final quality gate"

    mode = str(scan_mode or "").lower()
    intraday_weight = 1.25 if "intraday" in mode or "premarket" in mode else 1.0
    swing_weight = 1.2 if "swing" in mode else 1.0
    df["ranking_score"] = (
        df["score"].abs() * 0.18
        + df["confidence_pct"] * 0.16
        + df["ml_probability"] * 0.16
        + df["technical_score"] * 0.14 * intraday_weight
        + df["premarket_grade"] * 0.12 * intraday_weight
        + df["profitability_score"] * 0.12 * swing_weight
        + df["quality_score"] * 0.08
        + df["expected_return"].clip(lower=0) * 0.45
        + df["risk_reward_effective"].clip(lower=0) * 6
        + df["data_reliability_score"] * 0.04
        + df["profit_factor"].clip(lower=0) * 4
        + df["backtest_win_rate"] * 0.04
        - df["stop_distance_pct"].clip(lower=0) * 0.35
        - df["risk_score"].clip(lower=0) * 0.08
        - df["max_drawdown"].clip(lower=0) * 0.05
    )

    def fallback_action(row: pd.Series) -> str:
        existing = str(row.get("action") or row.get("trade_type") or "").upper()
        if existing in {"BUY", "SELL", "BUY WATCH", "SELL WATCH", "WATCH", "HOLD", "AVOID"}:
            return existing
        if row["ranking_score"] >= 55 and row["confidence_pct"] >= 45:
            return "WATCH"
        return "AVOID"

    df["action"] = df.apply(fallback_action, axis=1)
    df["final_gate_status"] = "Fallback ranked after final quality gate"
    if "quality_filter_passed" in df.columns:
        df["quality_filter_passed"] = df["quality_filter_passed"].fillna(False)
    else:
        df["quality_filter_passed"] = False
    df = df.sort_values(by="ranking_score", ascending=False).head(max(int(top_n or 10), 1))
    df["rank"] = range(1, len(df) + 1)
    return df


def build_insider_data(
    df: pd.DataFrame,
    event_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    direct_insider = (event_snapshot or {}).get("insider_activity") or {}
    if direct_insider.get("data_quality") in {"real", "partial"}:
        return direct_insider

    recent_return = ((df["Close"].iloc[-1] / df["Close"].iloc[-11]) - 1) * 100
    buy_value = clamp(50 + max(recent_return, 0) * 6, 20, 150)
    sell_value = clamp(45 + max(-recent_return, 0) * 5, 20, 140)
    return {
        "buy_value": buy_value,
        "sell_value": sell_value,
        "net_transactions": int(clamp(abs(recent_return), 1, 6)),
        "promoter_change_percent": clamp(recent_return / 10, -2, 2),
        "source": "price_action_proxy",
        "data_quality": "proxy",
    }


def build_valuation_data(
    symbol: str,
    fundamentals: dict[str, float],
) -> dict[str, float]:
    sector = get_stock_sector(symbol)
    sector_defaults = {
        "BANKING": {"sector_pe": 18, "sector_pb": 2.2},
        "ENERGY": {"sector_pe": 16, "sector_pb": 2.5},
        "IT": {"sector_pe": 26, "sector_pb": 6.0},
    }.get(sector, {"sector_pe": 20, "sector_pb": 3.0})

    earnings_growth = max(fundamentals["eps_growth"], 1)
    return {
        "pe_ratio": fundamentals["pe_ratio"],
        "pb_ratio": fundamentals["pb_ratio"],
        "peg_ratio": clamp(fundamentals["pe_ratio"] / earnings_growth, 0.3, 4.5),
        "sector_pe": sector_defaults["sector_pe"],
        "sector_pb": sector_defaults["sector_pb"],
        "source": fundamentals.get("source", ""),
        "data_quality": fundamentals.get("data_quality", ""),
    }


def build_data_reliability_score(*datasets: dict[str, Any]) -> dict[str, Any]:
    quality_scores = {
        "real": 100,
        "partial": 65,
        "proxy": 25,
        "missing": 0,
        "": 0,
    }
    weights = {
        "fundamental": 0.35,
        "delivery": 0.20,
        "insider": 0.15,
        "options": 0.20,
        "events": 0.10,
    }
    named = dict(zip(weights.keys(), datasets))
    weighted_score = 0.0
    details: dict[str, str] = {}
    for name, weight in weights.items():
        data = named.get(name) or {}
        quality = str(data.get("data_quality") or data.get("source") or "missing").lower()
        if quality not in quality_scores:
            quality = "partial" if data else "missing"
        weighted_score += quality_scores[quality] * weight
        details[f"{name}_quality"] = quality

    return {
        "data_reliability_score": round(weighted_score, 2),
        **details,
    }


def build_macro_sentiment_inputs(
    global_market_data: dict[str, float],
    advanced_macro_data: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    dxy = advanced_macro_data.get("dxy", 0)
    us10y = advanced_macro_data.get("us10y", 0)
    vix = abs(global_market_data.get("vix", 0))
    fii_dii_input = {
        "fii": clamp((global_market_data.get("sp500", 0) - dxy) * 300, -2500, 2500),
        "dii": clamp((global_market_data.get("dow", 0) - us10y) * 220, -1800, 1800),
    }
    war_input = {
        "conflict_level": clamp(vix / 3, 0, 10),
        "oil_risk": clamp(max(dxy, 0) + (vix / 4), 0, 10),
        "regional_risk": clamp(vix / 4, 0, 10),
        "escalation": vix > 4.5,
    }
    return fii_dii_input, war_input


def safe_module_result(
    name: str,
    func: Any,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        result = func(*args, **kwargs)
        if isinstance(result, dict):
            result.setdefault("score", 0)
            result.setdefault("reason", "")
            return result
        return {"score": 0, "reason": f"{name} returned non-dict", "raw": {}}
    except Exception as exc:
        logger.error(f"{name} failed in orchestrator: {exc}")
        return {"score": 0, "reason": f"{name} error", "raw": {}}


def build_trade_summary(
    signal: str,
    top_drivers: list[dict[str, Any]],
    signal_reason: str,
) -> tuple[str, str]:
    if "BUY" in signal:
        trade_type = "BUY"
    elif "SELL" in signal:
        trade_type = "SELL"
    else:
        positive_score = sum(driver.get("score", 0) for driver in top_drivers)
        trade_type = "BUY WATCH" if positive_score >= 0 else "SELL WATCH"

    reason_parts: list[str] = []
    if signal_reason:
        reason_parts.append(signal_reason)

    for driver in top_drivers[:3]:
        driver_reason = str(driver.get("reason", "")).strip()
        module_name = str(driver.get("module", "")).replace("_", " ").title()
        if driver_reason:
            reason_parts.append(f"{module_name}: {driver_reason}")

    trade_reason = " | ".join(part for part in reason_parts if part)
    return trade_type, trade_reason or "No strong confirming reason"


def build_fast_module_results(
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    breadth_result: dict[str, Any],
    sector_df: pd.DataFrame | None = None,
) -> dict[str, dict[str, Any]]:
    module_results: dict[str, dict[str, Any]] = {
        "breadth_analysis": breadth_result,
        "breakout_analysis": safe_module_result("breakout_analysis", breakout_analysis, df),
        "gap_analysis": safe_module_result("gap_analysis", gap_analysis, df),
        "market_structure": safe_module_result("market_structure", market_structure_analysis, df),
        "momentum_analysis": safe_module_result("momentum_analysis", momentum_analysis, df),
        "pivot_analysis": safe_module_result("pivot_analysis", pivot_analysis, df),
        "smart_money_analysis": safe_module_result("smart_money_analysis", smart_money_analysis, df),
        "support_resistance": safe_module_result("support_resistance", support_resistance_analysis, df),
        "technical_analysis": safe_module_result("technical_analysis", technical_analysis, df),
        "trend_analysis": safe_module_result("trend_analysis", trend_analysis, df),
        "volatility_analysis": safe_module_result("volatility_analysis", volatility_analysis, df),
        "volume_analysis": safe_module_result("volume_analysis", volume_analysis, df),
        "vwap_analysis": safe_module_result("vwap_analysis", vwap_analysis, df),
    }

    if is_valid_df(benchmark_df, 20):
        module_results["correlation_analysis"] = safe_module_result(
            "correlation_analysis",
            correlation_analysis,
            df,
            benchmark_df,
            sector_df=sector_df if sector_df is not None and not sector_df.empty else None,
        )
        module_results["relative_strength"] = safe_module_result(
            "relative_strength",
            relative_strength_analysis,
            df,
            benchmark_df,
            sector_df=sector_df if sector_df is not None and not sector_df.empty else None,
        )

    if sector_df is not None and not sector_df.empty:
        module_results["sector_strength"] = safe_module_result(
            "sector_strength",
            sector_strength_analysis,
            df,
            sector_df,
        )

    return module_results


def build_backtest_strategy(sector_df: pd.DataFrame | None, benchmark_df: pd.DataFrame):
    def strategy(historical_df: pd.DataFrame) -> dict[str, Any]:
        aligned_sector_df = None
        if sector_df is not None and not sector_df.empty:
            aligned_sector_df = sector_df.loc[: historical_df.index[-1]]
            if aligned_sector_df.empty:
                aligned_sector_df = None

        aligned_benchmark_df = benchmark_df.loc[: historical_df.index[-1]]
        fast_results = build_fast_module_results(
            historical_df,
            aligned_benchmark_df,
            {"score": 0, "reason": "", "raw": {}},
            sector_df=aligned_sector_df,
        )
        score_data = calculate_score(fast_results)
        return {"score": score_data.get("final_score", 0)}

    return strategy


def build_quality_metrics(
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    sector_df: pd.DataFrame,
    include_walk_forward: bool = False,
    include_optimization: bool = False,
) -> dict[str, Any]:
    regime_result = detect_market_regime(df)
    strategy_func = build_backtest_strategy(
        sector_df if not sector_df.empty else None,
        benchmark_df,
    )
    strategy_result = run_strategy_test(
        df,
        strategy_func=strategy_func,
        score_threshold=12,
        holding_period=5,
    )
    metrics = strategy_result.get("metrics", {}) or {}
    walk_forward_metrics = {}
    optimization_metrics = {}

    if include_walk_forward and len(df) >= 140:
        walk_forward_df = run_walk_forward(
            df=df,
            strategy_func=strategy_func,
            train_window=100,
            test_window=20,
            score_threshold=12,
        )
        if not walk_forward_df.empty:
            walk_forward_metrics = {
                "segments": int(len(walk_forward_df)),
                "win_rate": round(float(walk_forward_df["win_rate"].fillna(0).mean()), 2) if "win_rate" in walk_forward_df else 0,
                "profit_factor": round(float(walk_forward_df["profit_factor"].fillna(0).mean()), 2) if "profit_factor" in walk_forward_df else 0,
                "avg_pnl": round(float(walk_forward_df["avg_pnl"].fillna(0).mean()), 2) if "avg_pnl" in walk_forward_df else 0,
                "max_drawdown": round(float(walk_forward_df["max_drawdown"].fillna(0).mean()), 2) if "max_drawdown" in walk_forward_df else 0,
            }

    if include_optimization and len(df) >= 140:
        optimization_df = optimize_strategy(
            df=df,
            strategy_func=strategy_func,
            score_thresholds=[10, 12, 15, 18],
            holding_periods=[3, 5, 7, 10],
        )
        if not optimization_df.empty:
            best_row = optimization_df.iloc[0]
            optimization_metrics = {
                "best_score_threshold": float(best_row.get("score_threshold", 0)),
                "best_holding_period": float(best_row.get("holding_period", 0)),
                "win_rate": round(float(best_row.get("win_rate", 0)), 2),
                "profit_factor": round(float(best_row.get("profit_factor", 0)), 2),
                "avg_pnl": round(float(best_row.get("avg_pnl", 0)), 2),
                "max_drawdown": round(float(best_row.get("max_drawdown", 0)), 2),
            }

    profitability_score = 0.0
    profitability_score += min(metrics.get("win_rate", 0), 100) * 0.25
    profitability_score += min(max(metrics.get("profit_factor", 0), 0), 5) * 10
    profitability_score += max(metrics.get("avg_pnl", 0), -10) * 2
    profitability_score -= max(metrics.get("max_drawdown", 0), 0) * 1.2
    profitability_score += regime_result.get("score", 0)
    if walk_forward_metrics:
        profitability_score += min(walk_forward_metrics.get("win_rate", 0), 100) * 0.10
        profitability_score += min(max(walk_forward_metrics.get("profit_factor", 0), 0), 5) * 4
        profitability_score -= max(walk_forward_metrics.get("max_drawdown", 0), 0) * 0.4
    if optimization_metrics:
        profitability_score += min(optimization_metrics.get("win_rate", 0), 100) * 0.08
        profitability_score += min(max(optimization_metrics.get("profit_factor", 0), 0), 5) * 4
        profitability_score -= max(optimization_metrics.get("max_drawdown", 0), 0) * 0.35

    quality_score = normalize_value(
        profitability_score,
        -20,
        80,
    )

    return {
        "regime_result": regime_result,
        "backtest_metrics": metrics,
        "walk_forward_metrics": walk_forward_metrics,
        "optimization_metrics": optimization_metrics,
        "profitability_score": round(profitability_score, 2),
        "quality_score": round(quality_score, 2),
    }


def score_fast_candidate(
    symbol: str,
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    breadth_result: dict[str, Any],
    sector_frames: dict[str, pd.DataFrame],
    should_cancel=None,
) -> dict[str, Any] | None:
    if should_cancel and should_cancel():
        return None
    if not is_valid_df(df):
        return None

    sector_symbol = get_sector_symbol(get_stock_sector(symbol))
    sector_df = sector_frames.get(sector_symbol, pd.DataFrame()) if sector_symbol else pd.DataFrame()
    module_results = build_fast_module_results(df, benchmark_df, breadth_result, sector_df=sector_df)
    score_data = calculate_score(module_results)
    confidence_data = calculate_confidence(module_results)
    final_score = score_data.get("final_score", 0)
    confidence_pct = confidence_data.get("confidence_pct", 0)
    risk_data = calculate_risk(
        {
            "volatility": float(df["Close"].pct_change().dropna().tail(20).std() * 100),
            "confidence_pct": confidence_pct,
        }
    )
    latest = df.iloc[-1]
    latest_timestamp = ""
    try:
        latest_timestamp = df.index[-1].isoformat()
    except Exception:
        latest_timestamp = str(df.index[-1])
    last_close = round(float(latest.get("Close", 0) or 0), 2)

    return {
        "stock": symbol,
        "sector": get_stock_sector(symbol) or "UNKNOWN",
        "live_price": last_close,
        "last_close": last_close,
        "open": round(float(latest.get("Open", 0) or 0), 2),
        "high": round(float(latest.get("High", 0) or 0), 2),
        "low": round(float(latest.get("Low", 0) or 0), 2),
        "volume": int(float(latest.get("Volume", 0) or 0)),
        "data_timestamp": latest_timestamp,
        "coarse_score": round(final_score, 2),
        "coarse_confidence": round(confidence_pct, 2),
        "coarse_risk": risk_data.get("risk_score", 0),
        "coarse_quality": round(final_score + (confidence_pct * 0.4) - (risk_data.get("risk_score", 0) * 0.5), 2),
    }


def analyze_stock(
    symbol: str,
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    breadth_result: dict[str, Any],
    sector_frames: dict[str, pd.DataFrame],
    global_market_data: dict[str, float],
    advanced_macro_data: dict[str, float],
    market_news: list[str],
    period: str,
    interval: str,
    include_walk_forward: bool = False,
    include_optimization: bool = False,
    market_open_analysis: bool = False,
    intraday_df: pd.DataFrame | None = None,
    market_open_time: str = "09:08",
    scan_mode: str = "standard",
    should_cancel=None,
) -> dict[str, Any] | None:
    if should_cancel and should_cancel():
        return None
    if not is_valid_df(df):
        return None

    sector_symbol = get_sector_symbol(get_stock_sector(symbol))
    sector_df = sector_frames.get(sector_symbol, pd.DataFrame()) if sector_symbol else pd.DataFrame()

    event_snapshot = build_event_snapshot(symbol)
    direct_market_news = event_snapshot.get("market_news", [])
    direct_stock_news = event_snapshot.get("stock_news", [])
    combined_market_news = merge_news_items(market_news, direct_market_news)
    combined_stock_news = merge_news_items(get_stock_news(symbol, limit=8), direct_stock_news)

    fundamentals = build_fundamentals(symbol, df)
    valuation_data = build_valuation_data(symbol, fundamentals)
    earnings_data = build_earnings_data(df, event_snapshot=event_snapshot)
    insider_data = build_insider_data(df, event_snapshot=event_snapshot)
    delivery_data = build_delivery_data(df, event_snapshot=event_snapshot)
    options_data = get_options_data(symbol)
    event_quality = {
        "source": event_snapshot.get("source", ""),
        "data_quality": "partial" if any(
            event_snapshot.get(key)
            for key in ["earnings_events", "block_deals", "fii_dii_flow", "geopolitical_news", "market_news", "stock_news"]
        ) else "missing",
    }
    reliability_data = build_data_reliability_score(
        fundamentals,
        delivery_data,
        insider_data,
        options_data,
        event_quality,
    )
    quote_data = get_live_quote(symbol)
    live_price = quote_data.get("current_price") or get_live_price(symbol)
    macro_fii_dii_input, macro_war_input = build_macro_sentiment_inputs(
        global_market_data,
        advanced_macro_data,
    )
    direct_fii_dii = event_snapshot.get("fii_dii_flow", {}) or {}
    fii_dii_input = {
        "fii": direct_fii_dii.get("fii", macro_fii_dii_input.get("fii", 0)),
        "dii": direct_fii_dii.get("dii", macro_fii_dii_input.get("dii", 0)),
        "source": direct_fii_dii.get("source", "macro_proxy"),
        "confidence": direct_fii_dii.get("confidence", 0),
    }
    direct_geo = event_snapshot.get("geopolitical_snapshot", {}) or {}
    war_input = {
        "conflict_level": max(direct_geo.get("conflict_level", 0), macro_war_input.get("conflict_level", 0)),
        "oil_risk": max(direct_geo.get("oil_risk", 0), macro_war_input.get("oil_risk", 0)),
        "regional_risk": max(direct_geo.get("regional_risk", 0), macro_war_input.get("regional_risk", 0)),
        "escalation": bool(direct_geo.get("escalation", False) or macro_war_input.get("escalation", False)),
        "headline_count": direct_geo.get("headline_count", 0),
    }

    module_results = build_fast_module_results(df, benchmark_df, breadth_result, sector_df=sector_df)
    module_results.update(
        {
            "candlestick_analysis": safe_module_result("candlestick_analysis", candlestick_analysis, df),
            "chart_pattern_analysis": safe_module_result("chart_pattern_analysis", chart_pattern_analysis, df),
            "delivery_analysis": safe_module_result("delivery_analysis", delivery_analysis, df, delivery_data),
            "earnings_analysis": safe_module_result("earnings_analysis", earnings_analysis, df, earnings_data),
            "fibonacci_analysis": safe_module_result("fibonacci_analysis", fibonacci_analysis, df),
            "fundamentals_analysis": safe_module_result("fundamentals_analysis", fundamentals_analysis, df, fundamentals),
            "insider_activity": safe_module_result("insider_activity", insider_activity_analysis, df, insider_data),
            "liquidity_analysis": safe_module_result("liquidity_analysis", liquidity_analysis, df),
            "options_analysis": safe_module_result("options_analysis", options_analysis, df, options_data),
            "order_block_analysis": safe_module_result("order_block_analysis", order_block_analysis, df),
            "seasonality_analysis": safe_module_result("seasonality_analysis", seasonality_analysis, df),
            "valuation_analysis": safe_module_result("valuation_analysis", valuation_analysis, df, valuation_data),
            "news_sentiment": safe_module_result("news_sentiment", analyze_news_sentiment, combined_stock_news),
            "market_news_sentiment": safe_module_result("market_news_sentiment", analyze_news_sentiment, combined_market_news),
            "global_sentiment": safe_module_result("global_sentiment", analyze_global_sentiment, global_market_data),
            "fii_dii_analysis": safe_module_result("fii_dii_analysis", analyze_fii_dii, fii_dii_input),
            "war_analysis": safe_module_result("war_analysis", analyze_war_risk, war_input),
            "event_impact_analysis": safe_module_result("event_impact_analysis", event_impact_analysis, event_snapshot),
        }
    )

    score_data = calculate_score(module_results)
    confidence_data = calculate_confidence(module_results)
    final_score = score_data.get("final_score", 0)
    confidence_pct = confidence_data.get("confidence_pct", 0)
    realized_volatility = module_results["volatility_analysis"].get("raw", {}).get(
        "std_volatility",
        float(df["Close"].pct_change().dropna().tail(20).std() * 100),
    )
    risk_data = calculate_risk(
        {
            "volatility": realized_volatility,
            "confidence_pct": confidence_pct,
        }
    )

    primary_signal = generate_signal(
        final_score,
        confidence_pct,
        risk_data["risk_level"],
    )
    fallback_signal = generate_trade_signal(
        final_score,
        confidence_pct,
        risk_data["risk_level"],
    )
    signal = primary_signal.get("signal") or fallback_signal.get("signal", "HOLD")
    last_close = round(float(df["Close"].iloc[-1]), 2)
    gap_percent = module_results["gap_analysis"].get("raw", {}).get("gap_percent", 0)
    resolved_live_price = (
        round(float(live_price), 2)
        if isinstance(live_price, (int, float))
        else last_close
    )
    expected_open = quote_data.get("open")
    if not isinstance(expected_open, (int, float)) or expected_open <= 0:
        expected_open = round(
            resolved_live_price * (1 + (gap_percent / 100)),
            2,
        )
    targets = generate_targets(
        df,
        signal,
        score=final_score,
        live_price=resolved_live_price,
        expected_open=expected_open,
    )
    if targets:
        risk_data = calculate_risk(
            {
                "volatility": realized_volatility,
                "confidence_pct": confidence_pct,
                "entry": targets.get("entry", 0),
                "stoploss": targets.get("stoploss", 0),
                "target": targets.get("target2", 0),
                "account_capital": 100000,
            }
        )

    top_drivers = sorted(
        (
            {
                "module": module_name,
                "score": result.get("score", 0),
                "reason": result.get("reason", ""),
            }
            for module_name, result in module_results.items()
            if result.get("score", 0) != 0
        ),
        key=lambda item: abs(item["score"]),
        reverse=True,
    )[:5]
    trade_type, trade_reason = build_trade_summary(
        signal,
        top_drivers,
        primary_signal.get("reason") or fallback_signal.get("reason", ""),
    )
    quality_data = build_quality_metrics(
        df,
        benchmark_df,
        sector_df,
        include_walk_forward=include_walk_forward,
        include_optimization=include_optimization,
    )
    backtest_metrics = quality_data.get("backtest_metrics", {})
    regime_result = quality_data.get("regime_result", {})
    walk_forward_metrics = quality_data.get("walk_forward_metrics", {})
    optimization_metrics = quality_data.get("optimization_metrics", {})
    feature_vector = build_feature_vector(
        final_score=final_score,
        confidence_pct=confidence_pct,
        profitability_score=quality_data.get("profitability_score", 0),
        backtest_metrics=backtest_metrics,
        regime_result=regime_result,
        module_results=module_results,
    )
    model_probability = predict_probability(feature_vector)
    ml_probability = blend_probability(
        model_probability=model_probability,
        score=final_score,
        confidence_pct=confidence_pct,
        profitability_score=quality_data.get("profitability_score", 0),
    )
    category_scores = score_data.get("category_scores", {}) or {}

    def _module_score(name: str) -> float:
        try:
            return round(float(module_results.get(name, {}).get("score", 0) or 0), 2)
        except Exception:
            return 0.0

    def _module_reason(name: str) -> str:
        return str(module_results.get(name, {}).get("reason", "") or "")

    result_payload = {
        "stock": symbol,
        "scan_mode": scan_mode,
        "sector": get_stock_sector(symbol) or "UNKNOWN",
        "last_close": last_close,
        "score": round(final_score, 2),
        "technical_score": category_scores.get("technical_score", _module_score("technical_analysis")),
        "fundamental_score": _module_score("fundamentals_analysis"),
        "fundamental_source": fundamentals.get("source", ""),
        "fundamental_data_quality": fundamentals.get("data_quality", ""),
        **reliability_data,
        "volume_strength": category_scores.get("volume_score", _module_score("volume_analysis")),
        "breakout_strength": _module_score("breakout_analysis"),
        "momentum_score": category_scores.get("momentum_score", _module_score("momentum_analysis")),
        "trend_score": category_scores.get("trend_score", _module_score("trend_analysis")),
        "liquidity_score": category_scores.get("liquidity_score", _module_score("liquidity_analysis")),
        "market_strength_score": category_scores.get("market_strength_score", _module_score("breadth_analysis")),
        "sector_strength_score": category_scores.get("sector_strength_score", _module_score("sector_strength")),
        "technical_reason": _module_reason("technical_analysis"),
        "fundamental_reason": _module_reason("fundamentals_analysis"),
        "volume_reason": _module_reason("volume_analysis"),
        "breakout_reason": _module_reason("breakout_analysis"),
        "trend_reason": _module_reason("trend_analysis"),
        "confidence_pct": round(confidence_pct, 2),
        "final_opportunity_score": score_data.get("final_opportunity_score", 0),
        "opportunity_classification": score_data.get("opportunity_classification", "Ignore"),
        "risk_level": risk_data.get("risk_level", "Unknown"),
        "risk_score": risk_data.get("risk_score", 0),
        "recommended_risk_pct": risk_data.get("recommended_risk_pct", 0),
        "position_size": risk_data.get("position_size", 0),
        "expected_return": risk_data.get("expected_return", 0),
        "risk_reason": risk_data.get("reason", ""),
        "signal": signal,
        "trade_type": trade_type,
        "trade_reason": trade_reason,
        "ml_model_probability": model_probability,
        "ml_probability": ml_probability,
        "profitability_score": quality_data.get("profitability_score", 0),
        "quality_score": quality_data.get("quality_score", 0),
        "backtest_trades": backtest_metrics.get("trades", 0),
        "backtest_win_rate": backtest_metrics.get("win_rate", 0),
        "backtest_avg_pnl": backtest_metrics.get("avg_pnl", 0),
        "profit_factor": backtest_metrics.get("profit_factor", 0),
        "max_drawdown": backtest_metrics.get("max_drawdown", 0),
        "walk_forward_segments": walk_forward_metrics.get("segments", 0),
        "walk_forward_win_rate": walk_forward_metrics.get("win_rate", 0),
        "walk_forward_profit_factor": walk_forward_metrics.get("profit_factor", 0),
        "walk_forward_avg_pnl": walk_forward_metrics.get("avg_pnl", 0),
        "walk_forward_max_drawdown": walk_forward_metrics.get("max_drawdown", 0),
        "optimized_score_threshold": optimization_metrics.get("best_score_threshold", 0),
        "optimized_holding_period": optimization_metrics.get("best_holding_period", 0),
        "optimized_win_rate": optimization_metrics.get("win_rate", 0),
        "optimized_profit_factor": optimization_metrics.get("profit_factor", 0),
        "regime": regime_result.get("regime", "Unknown"),
        "trend_regime": regime_result.get("trend_regime", "Unknown"),
        "volatility_regime": regime_result.get("volatility_regime", "Unknown"),
        "signal_strength": primary_signal.get(
            "signal_strength",
            fallback_signal.get("signal_strength", 0),
        ),
        "bullish_modules": confidence_data.get("bullish_modules", 0),
        "bearish_modules": confidence_data.get("bearish_modules", 0),
        "event_score": module_results.get("event_impact_analysis", {}).get("score", 0),
        "event_reason": module_results.get("event_impact_analysis", {}).get("reason", ""),
        "delivery_source": delivery_data.get("source", ""),
        "delivery_data_quality": delivery_data.get("data_quality", ""),
        "insider_source": insider_data.get("source", ""),
        "insider_data_quality": insider_data.get("data_quality", ""),
        "options_source": options_data.get("source", ""),
        "options_data_quality": options_data.get("data_quality", ""),
        "earnings_date": earnings_data.get("earnings_date", ""),
        "days_to_earnings": event_snapshot.get("days_to_earnings"),
        "block_deal_count": len(event_snapshot.get("block_deals", []) or []),
        "geopolitical_headlines": direct_geo.get("headline_count", 0),
        "fii_source": fii_dii_input.get("source", ""),
        "top_drivers": top_drivers,
        "score_breakdown": score_data.get("breakdown", {}),
        **targets,
    }

    if market_open_analysis:
        result_payload["market_open_analysis"] = build_market_open_analysis(
            symbol=symbol,
            quote_data=quote_data,
            intraday_df=intraday_df,
            open_time=market_open_time,
        )
        result_payload["market_open_validation"] = build_market_open_validation(
            symbol=symbol,
            quote_data=quote_data,
            intraday_df=intraday_df,
            open_time=market_open_time,
        )

    premarket_data = evaluate_premarket_readiness(
        result_payload,
        module_results=module_results,
    )
    result_payload.update(premarket_data)

    return result_payload


def print_ranked_results(ranked: pd.DataFrame) -> None:
    if ranked.empty:
        safe_print("No stocks passed the ranking filters.")
        return

    display_columns = [
        "rank",
        "stock",
        "trade_type",
        "signal",
        "premarket_status",
        "premarket_action",
        "best_horizon",
        "premarket_grade",
        "setup_type",
        "score",
        "confidence_pct",
        "ml_probability",
        "quality_score",
        "profitability_score",
        "backtest_win_rate",
        "walk_forward_win_rate",
        "optimized_profit_factor",
        "profit_factor",
        "risk_level",
        "regime",
        "live_price",
        "expected_open",
        "last_close",
        "entry",
        "stoploss",
        "target1",
        "target2",
        "risk_reward",
        "trade_reason",
        "premarket_reasons",
    ]
    available = [column for column in display_columns if column in ranked.columns]
    safe_print(ranked[available].to_string(index=False))


def run_scan(args: argparse.Namespace) -> dict[str, Any]:
    safe_print("\n" + "=" * 60, flush=True)
    safe_print("STARTING SCAN: symbols={}, period={}".format(args.symbols, args.period), flush=True)
    safe_print("=" * 60, flush=True)
    
    logger.info("=" * 60)
    logger.info(f"STARTING SCAN: symbols={args.symbols}, period={args.period}")
    logger.info("=" * 60)

    import time
    start_time = time.time()

    def update_progress(pct: int, msg: str):
        setattr(args, "progress", pct)
        setattr(args, "status_message", msg)
        elapsed = time.time() - start_time
        if pct > 0:
            total_est = elapsed / (pct / 100.0)
            remaining = max(0.0, total_est - elapsed)
            setattr(args, "remaining_seconds", int(remaining))
        else:
            setattr(args, "remaining_seconds", -1)

    update_progress(0, "Initializing scan params...")
    filter_overrides = build_filter_overrides(args)
    profile = scanner_profile(getattr(args, "scan_mode", "standard"), getattr(args, "pipeline_stage", None))
    scan_metadata = build_scan_metadata(profile.mode, profile.stage)
    setattr(args, "scan_mode", profile.mode)
    setattr(args, "pipeline_stage", profile.stage)
    if int(getattr(args, "top_n", 0) or 0) <= 0:
        setattr(args, "top_n", profile.default_top_n)
    if int(getattr(args, "candidate_pool", 0) or 0) <= 0:
        setattr(args, "candidate_pool", profile.default_candidate_pool)
    if int(getattr(args, "validation_pool", 0) or 0) < 0:
        setattr(args, "validation_pool", profile.default_validation_pool)
    
    update_progress(3, "Loading symbols...")
    symbols = load_symbols(args)
    # cooperative cancellation: args may expose a `should_cancel()` callable
    should_cancel = getattr(args, "should_cancel", None)
    should_pause = getattr(args, "should_pause", None)
    def wait_if_paused(stage: str) -> None:
        while callable(should_pause) and should_pause():
            logger.info(f"Scan paused at {stage}")
            time.sleep(1)

    if callable(should_cancel) and should_cancel():
        logger.info("Scan cancelled before start: symbols loaded")
        return {"status": "cancelled", "message": "Scan cancelled by user.", "ranked": pd.DataFrame(), "results": [], "report_path": None}
    
    update_progress(5, f"Loaded {len(symbols)} symbols. Warming data...")
    safe_print(f"1. Loaded {len(symbols)} symbols", flush=True)
    logger.info(f"1. Loaded {len(symbols)} symbols")
    if not symbols:
        return {
            "status": "error",
            "message": "No symbols supplied.",
            "ranked": pd.DataFrame(),
            "results": [],
            "report_path": None,
        }

    logger.info("2. Starting fetch_all_stock_data...")
    update_progress(10, f"Fetching OHLCV data for {len(symbols)} symbols...")
    stock_frames = fetch_all_stock_data(
        symbols,
        period=args.period,
        interval=args.interval,
        workers=args.workers,
        should_cancel=should_cancel,
    )
    logger.info(f"   Got {len(stock_frames)} valid stock frames")
    
    if not stock_frames:
        logger.error("No valid stock data could be fetched")
        return {
            "status": "error",
            "message": "No valid stock data could be fetched.",
            "ranked": pd.DataFrame(),
            "results": [],
            "report_path": None,
        }

    wait_if_paused("after data fetch")
    if callable(should_cancel) and should_cancel():
        logger.info("Scan cancelled after data fetch")
        return {"status": "cancelled", "message": "Scan cancelled by user.", "ranked": pd.DataFrame(), "results": [], "report_path": None}

    logger.info("3. Fetching benchmark data...")
    update_progress(20, "Fetching benchmark and calculating breadth...")
    benchmark_df = fetch_symbol_data(
        args.benchmark,
        period=args.period,
        interval=args.interval,
    )
    logger.info("4. Building breadth payload...")
    breadth_payload = build_breadth_payload(stock_frames)
    breadth_result = (
        safe_module_result("breadth_analysis", breadth_analysis.run, breadth_payload)
        if breadth_payload
        else {"score": 0, "reason": "Breadth unavailable", "raw": {}}
    )
    logger.info("5. Fetching sector frames...")
    sector_frames = fetch_sector_frames(symbols, period=args.period, interval=args.interval)
    logger.info(f"   Got {len(sector_frames)} sector frames")
    
    logger.info("6. Scoring fast candidates...")
    update_progress(25, f"Scoring {len(symbols)} candidates...")
    coarse_results = []
    max_workers = max(1, min(args.workers, 32))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for symbol in symbols:
            df = stock_frames.get(symbol)
            if df is None:
                continue
            future = executor.submit(
                score_fast_candidate,
                symbol=symbol,
                df=df,
                benchmark_df=benchmark_df,
                breadth_result=breadth_result,
                sector_frames=sector_frames,
                should_cancel=should_cancel,
            )
            futures[future] = symbol

        completed_count = 0
        for future in as_completed(futures):
            symbol = futures[future]
            if callable(should_cancel) and should_cancel():
                logger.info(f"Scan cancelled during fast scoring at symbol {symbol}")
                for f in futures:
                    f.cancel()
                return {"status": "cancelled", "message": "Scan cancelled by user.", "ranked": pd.DataFrame(), "results": [], "report_path": None}
            wait_if_paused(f"fast scoring {symbol}")
            try:
                coarse_result = future.result()
                if coarse_result:
                    coarse_results.append(coarse_result)
            except Exception as e:
                logger.error(f"Error scoring candidate {symbol}: {e}", exc_info=True)
            completed_count += 1
            pct = 25 + int((completed_count / len(futures)) * 25)
            update_progress(pct, f"Fast screening: {completed_count}/{len(futures)} ({pct}%)")
            if completed_count % 100 == 0 or completed_count == len(futures):
                logger.info(f"   Scored {completed_count}/{len(futures)} symbols")

    logger.info(f"   {len(coarse_results)} candidates passed fast screening")
    
    if not coarse_results:
        logger.error("No candidates passed screening")
        return {
            "status": "error",
            "message": "No candidates passed the fast screening stage.",
            "ranked": pd.DataFrame(),
            "results": [],
            "report_path": None,
        }

    logger.info("7. Sorting candidates by quality...")
    update_progress(52, "Sorting candidates by quality score...")
    filtered_coarse_results = []
    rejected_fast_count = 0
    for coarse_result in coarse_results:
        passed, reasons = passes_fast_filter(
            coarse_result,
            strict=getattr(args, "strict_shortlist", False),
        )
        coarse_result["fast_filter_passed"] = passed
        coarse_result["fast_filter_reasons"] = " | ".join(reasons)
        if passed:
            filtered_coarse_results.append(coarse_result)
        else:
            rejected_fast_count += 1

    if not filtered_coarse_results:
        logger.warning("Strict fast filter removed all candidates; using top coarse candidates as fallback.")
        filtered_coarse_results = coarse_results

    logger.info(f"   Fast quality filter kept {len(filtered_coarse_results)} and rejected {rejected_fast_count}")
    coarse_df = pd.DataFrame(filtered_coarse_results).sort_values(
        by=["coarse_quality", "coarse_score", "coarse_confidence"],
        ascending=False,
    )
    candidate_symbols = coarse_df.head(max(args.top_n, args.candidate_pool))["stock"].tolist()
    logger.info(f"   Selecting {len(candidate_symbols)} candidates for deep analysis")
    
    logger.info("8. Fetching global market data...")
    update_progress(55, "Fetching macro risk indices...")
    global_market_data = get_global_market_data() or {}
    advanced_macro_data = get_advanced_macro_data() or {}
    market_news = get_market_news(limit=8)
    logger.info("9. Starting deep analysis phase...")

    market_open_frames: dict[str, pd.DataFrame] = {}
    if getattr(args, "market_open_analysis", False):
        logger.info("   Fetching intraday market-open data for filtered candidates...")
        update_progress(58, "Fetching intraday open frames...")
        market_open_frames = fetch_intraday_stock_data(
            candidate_symbols,
            period="1d",
            interval=args.market_open_interval,
            workers=args.workers,
        )
        logger.info(f"   Loaded intraday data for {len(market_open_frames)} candidate symbols")

    update_progress(60, f"Analyzing {len(candidate_symbols)} candidates...")
    results = []
    max_workers = max(1, min(args.workers, 20))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for idx, symbol in enumerate(candidate_symbols):
            df = stock_frames.get(symbol)
            if df is None:
                continue
            future = executor.submit(
                analyze_stock,
                symbol=symbol,
                df=df,
                benchmark_df=benchmark_df,
                breadth_result=breadth_result,
                sector_frames=sector_frames,
                global_market_data=global_market_data,
                advanced_macro_data=advanced_macro_data,
                market_news=market_news,
                period=args.period,
                interval=args.interval,
                include_walk_forward=False,
                include_optimization=False,
                market_open_analysis=getattr(args, "market_open_analysis", False),
                intraday_df=market_open_frames.get(symbol),
                market_open_time=args.market_open_time,
                scan_mode=getattr(args, "scan_mode", "standard"),
                should_cancel=should_cancel,
            )
            futures[future] = symbol

        completed_count = 0
        for future in as_completed(futures):
            symbol = futures[future]
            if callable(should_cancel) and should_cancel():
                logger.info(f"Scan cancelled during deep analysis at symbol {symbol}")
                for f in futures:
                    f.cancel()
                return {"status": "cancelled", "message": "Scan cancelled by user.", "ranked": pd.DataFrame(), "results": [], "report_path": None}
            wait_if_paused(f"deep analysis {symbol}")
            try:
                result = future.result()
                if result:
                    annotated = annotate_deep_filter(
                        result,
                        strict=getattr(args, "strict_shortlist", False),
                        overrides=filter_overrides,
                    )
                    results.append(annotated)
                    on_partial = getattr(args, "on_partial_result", None)
                    if callable(on_partial):
                        try:
                            on_partial(annotated)
                        except Exception as p_err:
                            logger.warning(f"Error invoking on_partial_result for {symbol}: {p_err}")
            except Exception as e:
                logger.error(f"Error during deep analysis for {symbol}: {e}", exc_info=True)
            completed_count += 1
            pct = 60 + int((completed_count / len(futures)) * 25)
            update_progress(pct, f"Deep analysis: {completed_count}/{len(futures)} ({pct}%)")
            logger.info(f"   Analyzed {symbol} ({completed_count}/{len(futures)})...")

    scan_mode = normalize_scan_mode(getattr(args, "scan_mode", ""))
    deep_validation_enabled = bool(getattr(args, "enable_deep_validation", False))
    skip_validation = (
        not deep_validation_enabled
        or "intraday" in scan_mode
        or "premarket" in scan_mode
        or int(getattr(args, "validation_pool", 0) or 0) <= 0
        or len(candidate_symbols) <= 3
    )

    if results and not skip_validation:
        preliminary_df = pd.DataFrame(results).sort_values(
            by=["ml_probability", "profitability_score", "score", "confidence_pct"],
            ascending=False,
        )
        validation_symbols = preliminary_df.head(max(args.top_n, args.validation_pool))["stock"].tolist()
        validation_symbol_set = set(validation_symbols)
        logger.info(f"10. Validating top {len(validation_symbols)} stocks with walk-forward...")
        update_progress(85, f"Validating {len(validation_symbols)} stocks...")
        max_workers = max(1, min(args.workers, 10))
        validated_result_map = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for result in results:
                symbol = result["stock"]
                if symbol not in validation_symbol_set:
                    continue
                df = stock_frames.get(symbol)
                if df is None:
                    continue
                future = executor.submit(
                    analyze_stock,
                    symbol=symbol,
                    df=df,
                    benchmark_df=benchmark_df,
                    breadth_result=breadth_result,
                    sector_frames=sector_frames,
                    global_market_data=global_market_data,
                    advanced_macro_data=advanced_macro_data,
                    market_news=market_news,
                    period=args.period,
                    interval=args.interval,
                    include_walk_forward=True,
                    include_optimization=True,
                    market_open_analysis=getattr(args, "market_open_analysis", False),
                    intraday_df=market_open_frames.get(result["stock"]),
                    market_open_time=args.market_open_time,
                    scan_mode=getattr(args, "scan_mode", "standard"),
                    should_cancel=should_cancel,
                )
                futures[future] = symbol

            completed_count = 0
            for future in as_completed(futures):
                symbol = futures[future]
                if callable(should_cancel) and should_cancel():
                    logger.info("Scan cancelled during validation phase")
                    for f in futures:
                        f.cancel()
                    return {"status": "cancelled", "message": "Scan cancelled by user.", "ranked": pd.DataFrame(), "results": [], "report_path": None}
                wait_if_paused(f"validation {symbol}")
                try:
                    validated_result = future.result()
                    if validated_result:
                        validated_result_map[symbol] = validated_result
                except Exception as e:
                    logger.error(f"Error during validation for {symbol}: {e}", exc_info=True)
                completed_count += 1
                pct = 85 + int((completed_count / len(futures)) * 10)
                update_progress(pct, f"Validation: {completed_count}/{len(futures)} ({pct}%)")
                logger.info(f"    Validated {symbol} ({completed_count}/{len(futures)})...")

        validated_results = []
        for result in results:
            symbol = result["stock"]
            if symbol in validation_symbol_set and symbol in validated_result_map:
                validated_results.append(
                    annotate_deep_filter(
                        validated_result_map[symbol],
                        strict=getattr(args, "strict_shortlist", False),
                        overrides=filter_overrides,
                    )
                )
            else:
                validated_results.append(result)

        results = validated_results
    elif results:
        if deep_validation_enabled:
            logger.info("10. Skipping walk-forward optimization for fast intraday/custom scan.")
        else:
            logger.info("10. Skipping walk-forward optimization because enable_deep_validation is false.")

    logger.info("11. Ranking final results...")
    update_progress(96, "Ranking final opportunity results...")
    wait_if_paused("ranking")
    if callable(should_cancel) and should_cancel():
        logger.info("Scan cancelled before ranking")
        return {"status": "cancelled", "message": "Scan cancelled by user.", "ranked": pd.DataFrame(), "results": [], "report_path": None}
    filter_passed_results = [
        result for result in results
        if result.get("quality_filter_passed", True)
    ]
    if not filter_passed_results:
        logger.warning("Deep quality filter removed all strict final candidates; fallback ranking analyzed candidates.")

    ranked = rank_stocks(
        filter_passed_results,
        min_score=15,
        min_confidence=45,
        top_n=args.top_n,
        strict_shortlist=args.strict_shortlist,
        min_expected_return_pct=getattr(args, "min_expected_return_pct", 0),
        min_ml_probability=getattr(args, "min_ml_probability", None),
        min_risk_reward=getattr(args, "min_risk_reward", None),
        max_stop_distance_pct=getattr(args, "max_stop_distance_pct", None),
        min_data_reliability_score=getattr(args, "min_data_reliability_score", None),
        min_profitability_score=getattr(args, "min_profitability_score", None),
    )
    fallback_ranked = False
    if ranked.empty and results:
        ranked = build_fallback_ranked_candidates(
            results,
            top_n=args.top_n,
            scan_mode=getattr(args, "scan_mode", ""),
        )
        fallback_ranked = not ranked.empty
        if fallback_ranked:
            strict_note = " Strict shortlist remains failed; rows are review candidates, not strict qualified trades." if getattr(args, "strict_shortlist", False) else ""
            logger.warning(
                f"Fallback ranking selected {len(ranked)} analyzed candidates because no stock passed every deep quality gate.{strict_note}"
            )

    logger.info(f"12. Generating report with {len(ranked)} ranked stocks...")
    update_progress(98, "Generating final report and excel sheet...")

    wait_if_paused("report generation")
    if callable(should_cancel) and should_cancel():
        logger.info("Scan cancelled before report generation")
        return {"status": "cancelled", "message": "Scan cancelled by user.", "ranked": pd.DataFrame(), "results": [], "report_path": None}

    report_candidate_results = filter_passed_results or results
    if not filter_passed_results and results:
        logger.warning("Using analyzed candidates for tiered report sheets because strict deep filter returned no final candidates.")

    quality_results_df = pd.DataFrame(report_candidate_results)
    filtered_sort_columns = [
        column
        for column in ["ml_probability", "premarket_grade", "profitability_score", "score", "confidence_pct"]
        if column in quality_results_df.columns
    ]
    filtered_150 = (
        (
            quality_results_df.sort_values(by=filtered_sort_columns, ascending=False)
            if filtered_sort_columns
            else quality_results_df
        ).head(150).to_dict(orient="records")
        if not quality_results_df.empty
        else []
    )
    top_25_source = quality_results_df
    top_25_sort_columns = [
        column
        for column in ["ml_probability", "profitability_score", "score", "confidence_pct", "coarse_quality"]
        if column in top_25_source.columns
    ]
    top_25 = (
        top_25_source.sort_values(by=top_25_sort_columns, ascending=False).head(25).to_dict(orient="records")
        if top_25_sort_columns and not top_25_source.empty
        else top_25_source.head(25).to_dict(orient="records")
        if not top_25_source.empty
        else []
    )
    if not ranked.empty:
        for key in ("scan_mode", "scan_family", "scanner_bucket", "pipeline_stage", "scanner_display_name"):
            ranked[key] = scan_metadata.get(key)

    filtered_150 = tag_records(filtered_150, scan_metadata)
    top_25 = tag_records(top_25, scan_metadata)
    final_top_10 = ranked.head(10).to_dict(orient="records") if not ranked.empty else (top_25 or filtered_150)[:10]
    ranked_records = tag_records(ranked.to_dict(orient="records"), scan_metadata)
    results = tag_records(results, scan_metadata)
    coarse_records = tag_records(coarse_df.to_dict(orient="records"), scan_metadata)
    final_top_10 = tag_records(final_top_10, scan_metadata)
    report_path = generate_scan_report(
        ranked_records,
        all_results=coarse_records,
        filtered_results=filtered_150,
        top_results=top_25,
        final_results=final_top_10,
        scan_mode=getattr(args, "scan_mode", ""),
    )
    
    final_count_label = "fallback-ranked stocks" if fallback_ranked else "qualified stocks"
    logger.info(f"SCAN COMPLETE: {len(ranked)} {final_count_label}, report at {report_path}")
    logger.info("=" * 60)

    update_progress(100, "Scan completed.")

    scan_output = {
        "status": "ok",
        "message": (
            "Scan completed with fallback-ranked analyzed candidates."
            if fallback_ranked
            else "Scan completed."
            if not ranked.empty
            else "Scan completed but no stocks qualified."
        ),
        "ranked": ranked,
        "results": results,
        "fallback_ranked": fallback_ranked,
        "all_stocks_live_data": coarse_records,
        "filtered_150": filtered_150,
        "top_25": top_25,
        "final_top_10": final_top_10,
        **scan_metadata,
        "report_path": report_path,
        "symbols_scanned": len(symbols),
        "candidates_considered": len(candidate_symbols),
        "breadth": breadth_payload,
        "breadth_result": breadth_result,
        "benchmark": args.benchmark,
        "period": args.period,
        "interval": args.interval,
        "scan_params": {
            "symbols": symbols,
            "period": args.period,
            "interval": args.interval,
            "scan_mode": getattr(args, "scan_mode", ""),
            "scan_family": scan_metadata["scan_family"],
            "scanner_bucket": scan_metadata["scanner_bucket"],
            "pipeline_stage": scan_metadata["pipeline_stage"],
            "benchmark": args.benchmark,
            "top_n": args.top_n,
            "candidate_pool": args.candidate_pool,
            "validation_pool": args.validation_pool,
            "enable_deep_validation": getattr(args, "enable_deep_validation", False),
            "strict_shortlist": args.strict_shortlist,
            "filter_overrides": filter_overrides,
            "min_expected_return_pct": getattr(args, "min_expected_return_pct", 0),
            "min_ml_probability": getattr(args, "min_ml_probability", None),
            "min_risk_reward": getattr(args, "min_risk_reward", None),
            "max_stop_distance_pct": getattr(args, "max_stop_distance_pct", None),
            "min_data_reliability_score": getattr(args, "min_data_reliability_score", None),
            "min_profitability_score": getattr(args, "min_profitability_score", None),
            "market_open_analysis": getattr(args, "market_open_analysis", False),
            "market_open_time": args.market_open_time,
            "market_open_interval": args.market_open_interval,
            "notify_telegram": getattr(args, "notify_telegram", False),
            "telegram_category": getattr(args, "telegram_category", "Premarket"),
        },
    }

    try:
        dispatch_scan_telegram(scan_output, args)
    except Exception as exc:
        logger.error(f"Telegram dispatch error: {exc}")

    return scan_output


def main() -> None:
    args = parse_args()
    safe_print("===== STARTING MULTI-FACTOR STOCK SCANNER =====")
    scan_output = run_scan(args)

    if scan_output.get("status") != "ok":
        safe_print(scan_output.get("message", "Scan failed."))
        return

    ranked = scan_output.get("ranked", pd.DataFrame())
    print_ranked_results(ranked)

    if ranked.empty:
        safe_print("Report skipped because no stocks qualified.")
        return

    report_path = scan_output.get("report_path")
    if report_path:
        safe_print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
