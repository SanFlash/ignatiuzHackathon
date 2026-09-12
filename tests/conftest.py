import pytest
from app import create_app
from app.repositories.repository import InMemoryRepository
from app.services.ai_service import AIService
from app.seed import DEMO_ID

@pytest.fixture
def app():
    return create_app({'TESTING': True, 'SECRET_KEY': 'testing-secret', 'RECRUITER_PASSWORD': '',
                       'SUPABASE_URL': '', 'SUPABASE_KEY': ''}, InMemoryRepository(), AIService())
@pytest.fixture
def repo(app): return app.extensions['repo']
@pytest.fixture
def service(app): return app.extensions['assessment_service']
@pytest.fixture
def client(app): return app.test_client()

def csrf(client):
    client.get('/')
    with client.session_transaction() as session: return session['csrf_token']

def start_client(client):
    result = client.post(f'/assessment/{DEMO_ID}/start', data={'csrf_token': csrf(client), 'candidate_name': 'QA Candidate'})
    assert result.status_code == 302
    return result.location.rsplit('/', 1)[-1]

def best_answer(question):
    if question['question_type'] == 'MCQ': return question['correct_answer']
    return ' '.join(x.split('|')[0] for x in question['rubric']['concepts']) + ' Explain the approach carefully and test trade-offs with a concrete example.'

def complete(service, repo, attempt_id):
    seen = []
    while True:
        attempt = service.get_attempt(attempt_id)
        if attempt['status'] == 'completed': return seen
        question = next(q for q in repo.list_questions(attempt['assessment_id']) if q['id'] == attempt['current_question_id'])
        assert question['id'] not in seen
        seen.append(question['id'])
        assert len(seen) <= 100
        service.submit(attempt_id, question['id'], best_answer(question))
