"""Gunicorn settings for production. Loaded by the systemd unit:
gunicorn --config deploy/gunicorn.conf.py wsgi:app
"""

import multiprocessing
import os

# Listen on a unix socket, not a TCP port: only Nginx (same machine) can reach
# it, and nothing is exposed to the network directly. systemd creates
# /run/course-finder for us (RuntimeDirectory= in the unit).
bind = "unix:/run/course-finder/gunicorn.sock"
# Socket file permissions rw-rw----: the service user and the www-data group
# (Nginx) can connect; nobody else can.
umask = 0o007

# Gunicorn 25.1+ also opens a control socket for the `gunicornc` admin tool.
# Its default lives under $HOME, which is read-only under systemd's
# ProtectSystem=strict, so keep it in the runtime directory next to the main
# socket. Mode 0600 (the default) means only the service user can use it.
control_socket = "/run/course-finder/gunicorn.ctl"

# The classic starting point is 2 x CPU cores + 1 sync workers. Each worker is a
# separate process with its own database connection pool, so the total must stay
# under MySQL's max_connections; GUNICORN_WORKERS in .env overrides the formula.
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"

# A request still running after 30 s is stuck: kill the worker and start a new one.
timeout = 30
# On restart or reload, give in-flight requests this long to finish.
graceful_timeout = 30
# Recycle each worker after about 1,000 requests, so a slow memory leak can never
# grow without limit. The jitter stops all workers restarting at the same moment.
max_requests = 1000
max_requests_jitter = 100

# Trust X-Forwarded-For / X-Forwarded-Proto from whoever connects. Safe here
# because only Nginx can open the unix socket.
forwarded_allow_ips = "*"

# Log to stdout/stderr; systemd sends both to the journal:
#   journalctl -u course-finder
accesslog = "-"
errorlog = "-"
loglevel = "info"

proc_name = "course-finder"
