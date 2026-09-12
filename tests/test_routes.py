from uuid import uuid4
from html.parser import HTMLParser
import pytest
from app.seed import DEMO_ID
from conftest import csrf, start_client, best_answer

@pytest.mark.parametrize('path',['/','/recruiter','/recruiter/assessments/new','/recruiter/login',
 f'/assessment/{DEMO_ID}/start',f'/recruiter/assessments/{DEMO_ID}/questions','/static/style.css','/static/app.js'])
def test_pages(client,path):
    response = client.get(path)
    assert response.status_code == 200 and response.headers['X-Content-Type-Options'] == 'nosniff'

def test_route_end_to_end(client,repo):
    aid = start_client(client)
    assert client.get(f'/assessment/{aid}').status_code == 200
    assert client.get(f'/report/{aid}').status_code == 409
    seen = []
    while True:
        response = client.get(f'/api/attempt/{aid}'); assert response.status_code == 200
        public = response.json; assert 'skill_state' not in public
        if public['status'] == 'completed': break
        q = public['question']; assert 'correct_answer' not in q and 'rubric' not in q
        assert q['id'] not in seen; seen.append(q['id']); assert len(seen) <= 15
        original = next(x for x in repo.list_questions(DEMO_ID) if x['id'] == q['id'])
        result = client.post(f'/assessment/{aid}/answer',data={'csrf_token':csrf(client),
                  'question_id':q['id'],'answer':best_answer(original)},follow_redirects=True)
        assert result.status_code == 200
    report = client.get(f'/report/{aid}')
    assert b'Competency profile' in report.data and b'INTERVIEW COPILOT' in report.data
    assert b'not an autonomous hiring decision' in report.data
    assert client.get(f'/assessment/{aid}').status_code == 302

def test_json_csrf_duplicate(client,repo):
    aid = start_client(client); q = client.get(f'/api/attempt/{aid}').json['question']
    stored = next(x for x in repo.list_questions(DEMO_ID) if x['id'] == q['id'])
    payload = {'question_id':q['id'],'answer':best_answer(stored)}; url = f'/assessment/{aid}/answer'
    assert client.post(url,json=payload).status_code == 400
    headers = {'X-CSRF-Token':csrf(client)}
    assert client.post(url,json=payload,headers=headers).status_code == 200
    assert client.post(url,json=payload,headers=headers).status_code == 409

def test_cross_browser_access(app,client):
    aid = start_client(client); stranger = app.test_client()
    assert stranger.get(f'/api/attempt/{aid}').status_code == 403
    assert stranger.get(f'/assessment/{aid}').status_code == 403

@pytest.mark.parametrize('aid',['invalid',str(uuid4())])
def test_invalid_attempt(client,aid):
    assert client.get(f'/assessment/{aid}').status_code == 404
    assert client.get(f'/api/attempt/{aid}').status_code == 404

def test_recruiter_password(app,client):
    app.config['RECRUITER_PASSWORD'] = 'test-only-password'
    assert client.get('/recruiter').status_code == 302
    assert client.post('/recruiter/login',data={'csrf_token':csrf(client),'password':'wrong'}).status_code == 403
    assert client.post('/recruiter/login',data={'csrf_token':csrf(client),'password':'test-only-password'}).status_code == 302
    assert client.get('/recruiter').status_code == 200

def test_creation_ui(client):
    result = client.post('/recruiter/assessments/new',data={'csrf_token':csrf(client),'title':'QA test',
      'job_title':'QA Engineer','description':'Functional test design','competencies':'Testing',
      'max_questions':'4','confidence_target':'0.7'})
    assert result.status_code == 302
    url = result.location; assert client.get(url).status_code == 200
    result = client.post(url,data={'csrf_token':csrf(client),'question_text':'Explain a regression test.',
      'question_type':'Subjective','skill':'Testing','difficulty':'2','points':'1','rubric':'regression, test, bug'})
    assert result.status_code == 302 and b'Explain a regression test.' in client.get(url).data

def test_safe_database_error(client,repo,monkeypatch):
    def fail(): raise RuntimeError('super-secret database password')
    monkeypatch.setattr(repo,'list_assessments',fail); result = client.get('/')
    assert result.status_code == 503 and b'super-secret' not in result.data and b'Traceback' not in result.data

def test_xss(client,service):
    service.catalog.create_assessment({'title':'<script>alert(1)</script>','job_title':'QA','description':'test',
       'competencies':['Testing'],'max_questions':4,'confidence_target':.7})
    result = client.get('/')
    assert b'<script>alert(1)</script>' not in result.data and b'&lt;script&gt;' in result.data

def test_links_assets(client):
    class Links(HTMLParser):
        def __init__(self): super().__init__(); self.urls = []
        def handle_starttag(self,tag,attrs):
            for key,value in attrs:
                if key in ('href','src') and value.startswith('/'): self.urls.append(value.split('#')[0])
    parser = Links(); parser.feed(client.get('/').text)
    for url in set(parser.urls): assert client.get(url).status_code == 200,url
