# Gunicorn configuration
# Must stay at 1 worker — the polling scheduler runs as in-process background threads.
workers = 1
worker_class = "sync"
timeout = 120
accesslog = "-"
errorlog = "-"
