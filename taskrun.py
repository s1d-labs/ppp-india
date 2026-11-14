"""What every task of this family shares: time budget, HTTP session, pause, and the claim loop. A fix here reaches all tasks."""
import os
import time
from datetime import datetime, timezone

import requests
from scrape_hub_client import ca_bundle, stop_flag, timed_get

UA = "s1d-labs scraper (https://github.com/s1d-labs)"
BUDGET_S = float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600
DEADLINE = time.time() + BUDGET_S - 180
STOP = stop_flag(install=False)        # main() calls stop_flag() to install the SIGINT / SIGTERM handlers


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def time_up():
    return STOP.is_set() or time.time() > DEADLINE


def session():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.verify = ca_bundle()
    return s


def pause(hub, floor=1.0):
    time.sleep(max(floor, hub.settings.get("delay_ms", 0) / 1000))


def get(hub, s, url, timeout=120, **kw):
    """The response (any status), or None when the site did not answer. Counts the hub's request metrics."""
    return timed_get(hub, s, url, timeout=timeout, allow_redirects=True, **kw)


def run(hub, s, handlers, margin_min=0):
    """Claim items one by one and hand each to handlers[payload kind] -> (records, error). margin_min: do not claim an item
    when less time is left (a long shard that is cut off starts again from the start)."""
    margin = margin_min * 60 if BUDGET_S > 3 * margin_min * 60 else 0
    try:
        while not time_up():
            if hub.settings.get("paused"):
                time.sleep(30)                         # the hub holds us (site down, or the owner paused the project)
                continue
            if DEADLINE - time.time() < margin:
                break                                  # too little time left for a whole item: leave it to a fresh worker
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            item = items[0]
            kind = item["payload"].get("kind")
            if kind not in handlers:
                hub.complete([item["key"]], "failed", error=f"unknown item kind {kind!r}")
                continue
            n, err = handlers[kind](hub, s, item)
            if err:
                hub.complete([item["key"]], "failed", error=err[:200])
            else:
                hub.complete([item["key"]], "done", fetched=n)
            pause(hub)
        if STOP.is_set():
            hub.close("failed", "stopped by signal")
        else:
            hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise
