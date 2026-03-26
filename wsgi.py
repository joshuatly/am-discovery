"""Gunicorn WSGI entry point.

Gunicorn serves the app directly without calling server.main(), so the
background polling scheduler must be initialised here.
"""

import logging
import time

import db
from server import app, load_config, trigger_poll_now, _schedule_next, _schedule_watchlist_next

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

db.init_db()

cfg = load_config()
interval_sec = cfg.get("newrelease_poll_interval_days", 1) * 86400
last_run = db.get_last_run()

if last_run and last_run.get("ran_at"):
    elapsed = time.time() - last_run["ran_at"]
    if elapsed < interval_sec:
        _schedule_next(override_delay=interval_sec - elapsed)
    else:
        trigger_poll_now()
else:
    trigger_poll_now()

_schedule_watchlist_next()
