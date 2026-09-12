"""Render production server. Keep one worker while using in-memory demo data."""
import os

bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
workers = 1
worker_class = 'gthread'
threads = 8
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = '-'
errorlog = '-'
capture_output = True
# Worker recycling would erase in-memory attempts, so do not enable it in demo.
max_requests = 0
