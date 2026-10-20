"""Daily official market feed refresh while the local EZstimate server is running.

Only observed BLS/EIA values enter the local database. There are no quote writes.
"""
from __future__ import annotations
import logging
import os
import threading

from .market_feeds import refresh_official_feeds

_LOG = logging.getLogger("ezstimate.market")


def start_market_refresh(*, interval_seconds=86400, refresh=None, stop_event=None):
    """Start a daemon that refreshes now and every 24 hours until server exits.

    Set EZSTIMATE_MARKET_AUTO_REFRESH=0 to disable. This is only called by
    server.main(), never on Flask import or in test clients.
    """
    if os.environ.get("EZSTIMATE_MARKET_AUTO_REFRESH", "1").lower() in ("0", "false", "off"):
        return None
    if not isinstance(interval_seconds,(int,float)) or interval_seconds <= 0:
        raise ValueError("Refresh interval must be positive")
    fetch = refresh or refresh_official_feeds
    stop = stop_event if stop_event is not None else threading.Event()

    def worker():
        while not stop.is_set():
            try:
                report = fetch()
                _LOG.info("Market refresh status=%s saved=%s unchanged=%s conflicts=%s",
                          report.get("status"),report.get("saved"),report.get("unchanged"),
                          report.get("conflicts"))
            except Exception:
                # No secrets, URLs or sensitive raw provider responses in logs.
                _LOG.warning("Market refresh failed; prior observations retained")
            if stop.wait(interval_seconds):
                break

    thread = threading.Thread(target=worker, name="EZstimatePublicMarketRefresh", daemon=True)
    thread.start()
    return thread
