#!/usr/bin/env python3
"""
Launcher script for the Stock Scanner desktop application.
Starts the aiohttp server and opens the web UI in the default browser.
"""

import sys
import webbrowser
import time
from pathlib import Path
from threading import Thread

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aiohttp import web
from ui.app import create_app
from utils.logger import logger


def start_server() -> None:
    """Start the aiohttp web server."""
    app = create_app()
    runner = web.AppRunner(app)

    async def run():
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 5000)
        await site.start()
        logger.info("Server started at http://127.0.0.1:5000")

    import asyncio
    asyncio.run(run())


def main() -> None:
    """Launch the server and open the browser."""
    logger.info("Stock Scanner Launcher")
    logger.info("=" * 50)

    # Start server in background thread
    server_thread = Thread(target=start_server, daemon=True)
    server_thread.start()

    # Give server time to start
    time.sleep(2)

    # Open browser
    url = "http://127.0.0.1:5000"
    logger.info(f"Opening browser to {url}")
    webbrowser.open(url)

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)


if __name__ == "__main__":
    main()