"""Live HTTP smoke test. Start run.py first. Uses only the standard library.
Creates disposable demo attempts and one recruiter-created assessment.
"""
import json
import sys
import os
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import build_opener, HTTPCookieProcessor, Request

BASE = 'http://127.0.0.1:5000'

class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.fields = {}; self.links = []; self.text = []
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and 'name' in attrs: self.fields[attrs['name']] = attrs.get('value', '')
        if tag in ('a','link','script'):
            path = attrs.get('href') or attrs.get('src')
            if path and path.startswith('/'): self.links.append(path.split('#')[0])
    def handle_data(self, data): self.text.append(data)


def run(recruiter_password=""):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    requests = 0
    def fetch(path, data=None):
        nonlocal requests
        request = Request(urljoin(BASE,path),data=urlencode(data).encode() if data is not None else None)
        with opener.open(request,timeout=30) as response:
            requests += 1
            assert response.status == 200
            return response.geturl(), response.read().decode()
    _, home = fetch('/')
    assert 'DEMO MODE' in home
    for path in set(Page(home).links): fetch(path)
    if recruiter_password:
        _, login = fetch('/recruiter/login')
        fetch('/recruiter/login', {'csrf_token': Page(login).fields['csrf_token'], 'password': recruiter_password})
    _, dashboard = fetch('/recruiter'); assert 'RECRUITER WORKSPACE' in dashboard
    start_path = next(x for x in Page(home).links if x.endswith('/start'))
    _, start = fetch(start_path)
    attempt_url, html = fetch(start_path, {'csrf_token':Page(start).fields['csrf_token'],'candidate_name':'HTTP Smoke Candidate'})
    aid = attempt_url.rsplit('/',1)[-1]
    seen, levels, confidences = [], [], []
    while '/report/' not in attempt_url:
        _, raw = fetch(f'/api/attempt/{aid}'); state = json.loads(raw); q = state['question']
        assert 'skill_state' not in state and not {'correct_answer','rubric'} & q.keys()
        assert q['id'] not in seen
        assert 'Recruiter workspace' not in html
        seen.append(q['id']); levels.append(q['difficulty']); assert len(seen) <= state['max_questions']
        answer = q['options'][0] if q['question_type'] == 'MCQ' else (
            'Use a reproducible example, logs and traces to isolate a concurrency race. '
            'Test the regression. A stateless API uses a load balancer, database and cache. '
            'Compare trade-offs, use an index and EXPLAIN the query plan. '
            'Use an idempotency key, persist the result and retry safely. '
            'A shared mutable default needs None and a fresh new list.')
        fields = Page(html).fields
        attempt_url,html = fetch(f'/assessment/{aid}/answer', {
            'csrf_token':fields['csrf_token'],'question_id':q['id'],'answer':answer})
    assert 'Competency profile' in html and 'INTERVIEW COPILOT' in html
    assert 'not an autonomous hiring decision' in html
    _, raw = fetch(f'/api/attempt/{aid}'); assert json.loads(raw)['status'] == 'completed'
    fields = Page(start).fields
    try:
        fetch(f'/assessment/{aid}/answer',{'csrf_token':fields['csrf_token'],'question_id':seen[-1],'answer':'late'})
        raise AssertionError('Completed attempt accepted another answer')
    except HTTPError as error: assert error.code == 409
    _, form = fetch('/recruiter/assessments/new')
    bank_url,bank = fetch('/recruiter/assessments/new',{'csrf_token':Page(form).fields['csrf_token'],
        'title':'HTTP smoke QA','job_title':'QA Engineer','description':'Live creation smoke test',
        'max_questions':'4','confidence_target':'.7','competencies':'Testing'})
    _,bank = fetch(bank_url,{'csrf_token':Page(bank).fields['csrf_token'],
        'skill':'Testing','question_type':'MCQ','difficulty':'2','points':'1',
        'question_text':'Which test protects a bug fix?','options':'Regression test\nNo test', 'correct_answer':'Regression test'})
    assert 'Which test protects a bug fix?' in bank
    result = {'status':'passed','http_200_responses':requests,'unique_questions':len(seen),
              'difficulty_sequence':levels,'completed_attempt_rejected':True,
              'report_generated':True,'recruiter_creation':True,'demo_mode':True,
              'browser_visual_validation':False}
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    if '--spawn' not in sys.argv:
        run()
    else:
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, DATABASE_MODE='demo', SUPABASE_URL='', SUPABASE_KEY='', OPENAI_API_KEY='',
                   RECRUITER_PASSWORD='', COOKIE_SECURE='false')
        with (root / 'docs' / 'http-server.log').open('w') as log:
            process = subprocess.Popen([sys.executable, 'run.py'], cwd=root, env=env, stdout=log, stderr=log)
            try:
                for _ in range(50):
                    if process.poll() is not None:
                        raise RuntimeError('Flask server exited; inspect docs/http-server.log')
                    try:
                        with build_opener().open(BASE, timeout=1) as response:
                            if response.status == 200: break
                    except URLError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Flask did not start within five seconds')
                run()
            finally:
                process.terminate()
                process.wait(timeout=5)
