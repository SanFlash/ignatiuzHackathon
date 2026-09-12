import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app import create_app
from app.diagnostics import describe_failure
from app.repositories.repository import InMemoryRepository
from app.services.ai_service import AIService
from app.services.assessment_service import AssessmentService
from app.services.question_service import QuestionService
from app.seed import DEMO_ID
from conftest import best_answer


def generated(payload, instruction, max_tokens=360):
    kind = payload['type']
    return {'question_text': f"In {payload['skill']}, explain a practical case at level {payload['difficulty']}?",
            'options': ['Correct generated option', 'Wrong one', 'Wrong two', 'Wrong three'] if kind == 'MCQ' else [],
            'correct_answer': 'Correct generated option' if kind == 'MCQ' else None,
            'concepts': ['test', 'example', 'reason'] if kind == 'Subjective' else []}


@pytest.fixture
def generated_service(repo):
    ai = AIService(generate_questions=True, local_evaluation=True)
    ai.client = object()
    ai._json = Mock(side_effect=generated)
    return AssessmentService(repo, ai)


def test_generated_question_saved_and_reload_free(generated_service, repo):
    s = generated_service; a = s.start(DEMO_ID)
    original = repo.get_attempt(a['id'])
    assert original['question_override']['origin'] == 'openai'
    for _ in range(3):
        public = s.public_attempt(a['id'])
        assert public['question']['question_text'] == original['question_override']['question_text']
        assert not {'correct_answer', 'rubric', 'origin'} & public['question'].keys()
    assert s.ai._json.call_count == 1


def test_grade_exact_displayed_mcq_not_bank(generated_service, repo):
    s = generated_service; a = s.start(DEMO_ID)
    # Select a known bank MCQ, then construct the override as the real workflow would.
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type'] == 'MCQ')
    a['current_question_id'] = q['id']; a['question_override'] = s.questions.prepare(q); repo.save_attempt(a)
    s.submit(a['id'], q['id'], 'Correct generated option')
    response = repo.list_responses(a['id'])[0]
    assert response['evaluation']['score'] == 100
    assert response['evaluation']['question_snapshot']['correct_answer'] == 'Correct generated option'
    assert s.ai._json.call_args.args[0]['last']['answer'] == 'Correct generated option'


def test_generation_context_bounded(generated_service, repo):
    q = repo.list_questions(DEMO_ID)[0]
    generated_service.questions.prepare(q, q, 'a'*20000, {'score': 0, 'weaknesses': ['x'*1000]*20}, ['y'*1000]*100)
    payload = generated_service.ai._json.call_args.args[0]
    assert len(payload['last']['answer']) == 800
    assert len(payload['last']['gaps']) == 3
    assert len(payload['avoid']) == 5
    assert all(len(x) <= 160 for x in payload['avoid'])
    assert len(json.dumps(payload)) < 3000
    assert generated_service.ai._json.call_args.kwargs['max_tokens'] == 360


@pytest.mark.parametrize('failure', [TimeoutError(), RuntimeError('429'), RuntimeError('401'), RuntimeError('402')])
def test_provider_failure_falls_back_and_cools_down(generated_service, repo, failure):
    s = generated_service; s.ai._json = Mock(side_effect=failure)
    a = s.start(DEMO_ID)
    assert a['question_override'] is None
    q = next(q for q in repo.list_questions(DEMO_ID) if q['id'] == a['current_question_id'])
    s.submit(a['id'],q['id'],best_answer(q))
    assert s.get_attempt(a['id'])['version'] == 1
    assert s.ai._json.call_count == 1


@pytest.mark.parametrize('data', [None, {}, {'question_text': 'short'},
 {'question_text': 'Which option is actually correct?', 'options': ['A']*4, 'correct_answer': 'A'},
 {'question_text': 'Which option is actually correct?', 'options': ['A','B','C','D'], 'correct_answer': 'E'}])
def test_invalid_question_fallback(generated_service, repo, data):
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type'] == 'MCQ')
    generated_service.ai._json = Mock(return_value=data)
    assert generated_service.questions.prepare(q) is None


def test_duplicate_text_rejected(generated_service, repo):
    q = repo.list_questions(DEMO_ID)[0]; first = generated_service.questions.prepare(q)
    assert generated_service.questions.prepare(q, seen=[first['question_text'].upper()]) is None


def test_end_to_end_generated_without_report_call(generated_service, repo):
    s = generated_service; a = s.start(DEMO_ID); count = 0
    while a['status'] == 'active':
        q = a['question_override'] or next(q for q in repo.list_questions(DEMO_ID) if q['id'] == a['current_question_id'])
        s.submit(a['id'],q['id'],best_answer(q)); count += 1; a = s.get_attempt(a['id'])
    assert s.ai._json.call_count == count  # initial + next questions, no report/LLM grading calls
    report = s.report(a['id'])
    assert report['coverage'] == 100 and all(e['question_text'] for e in report['evidence'])


def test_sdk_endpoint_and_budget(monkeypatch):
    ai = AIService('test-key', 'vendor/model')
    assert str(ai.client.base_url) == 'https://api.openai.com/v1/'
    create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))]))
    monkeypatch.setattr(ai.client.chat.completions, 'create', create)
    ai._json({'skill':'SQL'}, 'Return JSON')
    assert create.call_args.kwargs['max_completion_tokens'] == 360
    assert ai.client.max_retries == 0


def test_explicit_demo_ignores_stale_database_settings(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','')
    app = create_app({'TESTING':True,'DATABASE_MODE':'demo','SUPABASE_URL':'https://unused.supabase.co','SUPABASE_KEY':'unused'})
    assert app.extensions['repo'].demo and app.test_client().get('/').status_code == 200


def test_openai_key_alone_enables_questions_and_evaluation(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setenv('OPENAI_MODEL','')
    monkeypatch.setenv('OPENROUTER_API_KEY','ignored-legacy-key')
    monkeypatch.setenv('OPENAI_BASE_URL','https://unwanted.example/v1')
    app = create_app({'DATABASE_MODE':'demo'})
    ai = app.extensions['ai']
    assert ai.model == 'gpt-4o-mini' and not ai.local_evaluation and ai.generate_questions
    assert str(ai.client.base_url) == 'https://api.openai.com/v1/'


def test_no_openai_key_uses_local_even_with_old_router_settings(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','ignored-legacy-key')
    monkeypatch.setenv('OPENROUTER_MODEL','old-model')
    monkeypatch.setenv('OPENAI_API_KEY','')
    assert create_app({'DATABASE_MODE':'demo'}).extensions['ai'].client is None


@pytest.mark.parametrize('code, expected', [('PGRST205','DB_SCHEMA_MISSING'),('42703','DB_SCHEMA_MISSING'),('42501','DB_ACCESS_DENIED')])
def test_actionable_db_codes(code,expected):
    exc = RuntimeError('do not expose credentials'); exc.code = code
    assert describe_failure(exc,True)[0] == expected


def test_503_reference_and_no_secret(client,repo,monkeypatch):
    def fail(): raise RuntimeError('password=very-secret')
    monkeypatch.setattr(repo,'list_assessments',fail)
    response = client.get('/')
    assert response.status_code == 503 and b'APP_ERROR' in response.data and b'Reference:' in response.data
    assert b'very-secret' not in response.data


def test_doctor_command(app):
    result = app.test_cli_runner().invoke(args=['doctor'])
    assert result.exit_code == 0 and 'Database read OK' in result.output

def test_sdk_initialization_failure_keeps_app_running(monkeypatch):
    import openai
    monkeypatch.setattr(openai, 'OpenAI', Mock(side_effect=ImportError('proxy dependency unavailable')))
    ai = AIService('test-key','vendor/model',generate_questions=True)
    assert ai.client is None
    app = create_app({'DATABASE_MODE':'demo'}, ai_service=ai)
    assert app.test_client().get('/').status_code == 200


def test_live_sdk_invalid_json_generation_falls_back(repo):
    from openai import OpenAI
    import httpx
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':'test',
              'choices':[{'index':0,'message':{'role':'assistant','content':'not valid json'},'finish_reason':'stop'}]})
    ai = AIService(generate_questions=True,local_evaluation=True)
    ai.client = OpenAI(api_key='test-key',base_url='https://api.openai.com/v1',
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    service = AssessmentService(repo,ai)
    attempt = service.start(DEMO_ID)
    assert attempt['question_override'] is None and attempt['current_question_id']
    assert requests[0]['max_completion_tokens'] == 360


def test_missing_schema_safe_recovery_message(app,repo,monkeypatch):
    from postgrest.exceptions import APIError
    repo.demo = False
    def fail():
        raise APIError({'code':'PGRST205','message':'private database details','hint':'','details':''})
    monkeypatch.setattr(repo,'list_assessments',fail)
    response = app.test_client().get('/')
    assert response.status_code == 503
    assert b'DB_SCHEMA_MISSING' in response.data and b'DATABASE_MODE=demo' in response.data
    assert b'private database details' not in response.data

def test_openai_generation_and_grading_complete_flow(repo):
    """Real SDK and app services, simulated OpenAI HTTP responses; no external key/network."""
    import httpx
    from openai import OpenAI
    calls = []
    def handle(request):
        body = json.loads(request.content)
        payload = json.loads(body['messages'][1]['content'])
        calls.append(body)
        assert request.url.host == 'api.openai.com'
        if 'type' in payload:
            output = generated(payload, '', 360)
        else:
            output = {'correctness':1, 'strengths':['Relevant explanation'], 'weaknesses':[],
                      'evidence':[payload['answer'][:20]], 'feedback':'Clear technical evidence.'}
        return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':'gpt-4o-mini',
            'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps(output)},'finish_reason':'stop'}]})
    ai = AIService(generate_questions=True)
    ai.client = OpenAI(api_key='test-key',base_url='https://api.openai.com/v1',
                      http_client=httpx.Client(transport=httpx.MockTransport(handle)),max_retries=0)
    s = AssessmentService(repo,ai); a = s.start(DEMO_ID); count = subjective = 0
    while a['status'] == 'active':
        q = a['question_override']
        assert q and q['origin'] == 'openai'
        subjective += q['question_type'] == 'Subjective'
        s.submit(a['id'],q['id'],best_answer(q)); count += 1
        a = s.get_attempt(a['id'])
    assert len(calls) == count + subjective
    assert all(c['max_completion_tokens'] in (240,360) for c in calls)
    assert s.report(a['id'])['overall_score'] == 100
    assert any(r['evaluation']['source'] == 'llm' for r in repo.list_responses(a['id']))


def test_written_answer_budget_and_no_report_api(question=None):
    ai = AIService(); ai.client = object()
    ai._json = Mock(return_value={'correctness':.8,'strengths':[],'weaknesses':[],
                                 'evidence':['None'],'feedback':'Partial explanation.'})
    q = {'question_text':'Explain defaults','skill':'Python','difficulty':3,'rubric':{'concepts':['None']}}
    ai.evaluate_subjective(q,'Use None for fresh arguments.')
    assert ai._json.call_args.kwargs['max_tokens'] == 240
    ai.interview_questions({'Python':{'estimated_level':3,'confidence':.4,'evidence_count':1}})
    assert ai._json.call_count == 1
