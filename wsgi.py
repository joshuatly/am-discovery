"""Gunicorn WSGI entry point."""

import logging

from server import app, init_scheduler  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
init_scheduler()
