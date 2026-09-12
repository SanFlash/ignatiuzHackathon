"""Run the full HTTP workflow under the Render Gunicorn configuration (Linux)."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler
from urllib.error import URLError
import e2e_http

root = Path(__file__).resolve().parents[1]
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
password = secrets.token_urlsafe(24)
env = dict(os.environ, RENDER='true', PORT=str(port), SECRET_KEY=secrets.token_hex(32),
           RECRUITER_PASSWORD=password, DATABASE_MODE='demo', OPENAI_API_KEY='',
           SUPABASE_URL='', SUPABASE_KEY='', COOKIE_SECURE='false', NO_PROXY='127.0.0.1,localhost')
# Only the HTTP smoke overrides Secure cookies. HTTPS cookie behavior has a pytest check.
os.environ['NO_PROXY'] = env['NO_PROXY']
e2e_http.BASE = f'http://127.0.0.1:{port}'
with tempfile.TemporaryFile(mode='w+') as log:
    process = subprocess.Popen([sys.executable, '-m', 'gunicorn', '--config', 'gunicorn.conf.py', 'run:app'],
                               cwd=root, env=env, stdout=log, stderr=log)
    try:
        opener = build_opener(ProxyHandler({}))
        for _ in range(100):
            if process.poll() is not None:
                log.seek(0)
                raise RuntimeError(log.read())
            try:
                with opener.open(e2e_http.BASE + '/health', timeout=1) as response:
                    assert response.status == 200
                    assert json.load(response) == {'status': 'ok'}
                    assert response.headers.get('Set-Cookie') is None
                    break
            except URLError:
                time.sleep(.1)
        else:
            raise RuntimeError('Gunicorn did not become healthy')
        e2e_http.run(recruiter_password=password)
        print('Gunicorn Render-config health, recruiter login and full workflow: PASS')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
