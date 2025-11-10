"""
    Gunicorn workers-config file
    Logic to decide how many workers to launch based on .env variable `LIVE_GUNICORN_INSTANCES`
    NOTE: some gunicorn params (e.g. --name) don't seem to work from here so must be called from the command line
"""

import os
import multiprocessing

workers = os.environ.get("LIVE_GUNICORN_INSTANCES", '-1')

if workers == '-1':
    workers = multiprocessing.cpu_count() * 2
