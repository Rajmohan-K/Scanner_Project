#!/usr/bin/env python3
"""
Standalone background scheduler for automated stock scans.
Runs at specified times (default 9:00 AM IST) and saves results.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import DEFAULT_BENCHMARK, WATCHLIST, run_scan
from ui.storage import save_scan
from utils.logger import logger


def run_scheduled_scan(args: argparse.Namespace) -> None:
    """Execute a scan and save results."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{timestamp}] Starting scheduled scan with {len(args.symbols)} symbols...")

    try:
        scan_output = run_scan(args)

        if scan_output.get("status") == "ok":
            # Convert dataframes to serializable format
            body = {
                "status": scan_output.get("status"),
                "message": scan_output.get("message"),
                "report_path": scan_output.get("report_path"),
                "symbols_scanned": scan_output.get("symbols_scanned", 0),
                "candidates_considered": scan_output.get("candidates_considered", 0),
                "results": scan_output.get("results", []),
                "ranked": scan_output.get("ranked", []),
                "breadth": scan_output.get("breadth", {}),
            }

            scan_id = save_scan(body)
            logger.info(f"[{timestamp}] Scheduled scan completed. Scan ID: {scan_id}")
        else:
            logger.error(f"[{timestamp}] Scheduled scan failed: {scan_output.get('message')}")
    except Exception as e:
        logger.error(f"[{timestamp}] Scheduled scan error: {e}")


def create_scheduler(args: argparse.Namespace) -> BackgroundScheduler:
    """Create and configure the APScheduler scheduler."""
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # Parse time (format: HH:MM, e.g., "09:00")
    time_parts = args.schedule_time.split(":")
    hour = int(time_parts[0])
    minute = int(time_parts[1]) if len(time_parts) > 1 else 0

    # Schedule daily at specified time
    scheduler.add_job(
        run_scheduled_scan,
        "cron",
        hour=hour,
        minute=minute,
        args=[args],
        id="stock_scanner_job",
        name="Daily stock scan",
        timezone="Asia/Kolkata",
    )

    logger.info(f"Scheduler configured to run daily at {hour:02d}:{minute:02d} IST")
    return scheduler


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled stock scanner")
    parser.add_argument("--symbols", nargs="+", default=WATCHLIST)
    parser.add_argument("--period", default="6mo")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--candidate-pool", type=int, default=150)
    parser.add_argument("--validation-pool", type=int, default=25)
    parser.add_argument("--schedule-time", default="09:00", help="Time to run scan in HH:MM format (IST)")
    parser.add_argument("--run-now", action="store_true", help="Run scan immediately instead of waiting for schedule")

    args = parser.parse_args()

    logger.info("Starting scanner scheduler service...")
    logger.info("=" * 50)

    # Convert args to match run_scan signature
    args_for_scan = argparse.Namespace(
        symbols=args.symbols,
        period=args.period,
        interval=args.interval,
        benchmark=args.benchmark,
        top_n=args.top_n,
        workers=args.workers,
        symbols_file=None,
        candidate_pool=args.candidate_pool,
        validation_pool=args.validation_pool,
        strict_shortlist=False,
        auto_nse_universe=False,
        refresh_universe=False,
        universe_output="all_symbols.txt",
    )

    # Run immediately if requested
    if args.run_now:
        logger.info("Running scan immediately...")
        run_scheduled_scan(args_for_scan)

    # Start scheduler
    scheduler = create_scheduler(args)
    scheduler.start()

    logger.info("Scheduler running. Press Ctrl+C to stop.")

    try:
        while True:
            pass
    except KeyboardInterrupt:
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()