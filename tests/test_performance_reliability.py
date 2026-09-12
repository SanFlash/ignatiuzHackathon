from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import Mock
import pytest
from app.errors import Conflict
from app.seed import DEMO_ID
from app.services.question_service import QuestionService
from conftest import best_answer


def subjective_attempt(service, repo):
    a = service.start(DEMO_ID)
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type'] == 'Subjective')
    a['current_question_id'] = q['id']; repo.save_attempt(a)
    return a,q


def test_parallel_calls_share_answer_and_overlap(service,repo,monkeypatch):
    a,q = subjective_attempt(service,repo)
    service.ai.client = object(); service.ai.generate_questions = True
    barrier = Barrier(2)
    def grade(question,answer):
        barrier.wait(timeout=2)
        return service.ai.structured(question,.7,[],[],[answer],'Good evidence.','llm')
    def generate(selected,previous,answer,evaluation,seen):
        assert answer == 'Concrete technical explanation.' and evaluation is None
        barrier.wait(timeout=2)
        return dict(selected, question_text='New independently selected question?')
    monkeypatch.setattr(service.ai,'evaluate_subjective',grade)
    monkeypatch.setattr(service.questions,'prepare',generate)
    result = service.submit(a['id'],q['id'],'Concrete technical explanation.')
    assert result['question']['question_text'] == 'New independently selected question?'


def test_independent_selection_invariant_for_all_scores(service,repo):
    a,q = subjective_attempt(service,repo)
    assessment = repo.get_assessment(DEMO_ID); pool = repo.list_questions(DEMO_ID)
    chosen = service._independent_next(assessment,a,q,pool)
    assert chosen and chosen['skill'] != q['skill']
    for i in range(101):
        evaluation = service.ai.structured(q,i/100,[],[],[],'','test')
        state = service.engine.update(a['skill_state'],q['skill'],evaluation)
        actual = service.engine.select_question(pool,state,a['answered_ids']+[q['id']],assessment['priorities'])
        assert actual['id'] == chosen['id']


def test_no_parallel_guess_when_current_skill_can_win(service,repo):
    a,q = subjective_attempt(service,repo)
    for skill in a['skill_state']:
        if skill != q['skill']:
            a['skill_state'][skill]['evidence_count'] = 1
    assert service._independent_next(repo.get_assessment(DEMO_ID),a,q,repo.list_questions(DEMO_ID)) is None


def test_final_answer_never_prepares_next(service,repo,monkeypatch):
    a,q = subjective_attempt(service,repo)
    assessment = repo.get_assessment(DEMO_ID); assessment['max_questions'] = 4; repo.create_assessment(assessment)
    a['answered_ids'] = [x['id'] for x in repo.list_questions(DEMO_ID) if x['id'] != q['id']][:3]
    repo.save_attempt(a)
    service.ai.client = object(); service.ai.generate_questions = True
    monkeypatch.setattr(service.ai,'evaluate_subjective',lambda q,a: service.ai.structured(q,.5,[],[],[], 'ok','test'))
    prepare = Mock(); monkeypatch.setattr(service.questions,'prepare',prepare)
    result = service.submit(a['id'],q['id'],'Answer')
    assert result['status'] == 'completed' and result['progress'] == 100
    prepare.assert_not_called()


def test_duplicate_processing_rejected_before_ai_cost(service,repo,monkeypatch):
    a,q = subjective_attempt(service,repo)
    entered,release = Event(),Event()
    original = service.ai.evaluate_subjective
    calls = []
    def grade(question,answer):
        calls.append(answer); entered.set(); assert release.wait(2)
        return original(question,answer)
    monkeypatch.setattr(service.ai,'evaluate_subjective',grade)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(service.submit,a['id'],q['id'],'test answer')
        assert entered.wait(2)
        try:
            with pytest.raises(Conflict,match='processing'):
                service.submit(a['id'],q['id'],'test answer')
        finally:
            release.set()
        assert first.result()['answered_count'] == 1
    assert len(calls) == 1 and len(repo.list_responses(a['id'])) == 1


def test_submission_does_not_reread_after_commit(service,repo,monkeypatch):
    a,q = subjective_attempt(service,repo)
    original = repo.commit_answer
    def commit(*args):
        original(*args)
        monkeypatch.setattr(repo,'list_questions',Mock(side_effect=AssertionError('Unnecessary post-commit read')))
        monkeypatch.setattr(repo,'get_assessment',Mock(side_effect=AssertionError('Unnecessary post-commit read')))
        monkeypatch.setattr(repo,'get_attempt',Mock(side_effect=AssertionError('Unnecessary post-commit read')))
    monkeypatch.setattr(repo,'commit_answer',commit)
    assert service.submit(a['id'],q['id'],best_answer(q))['answered_count'] == 1


def test_generated_mcq_whitespace_normalized(repo):
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type']=='MCQ')
    data = {'question_text':'Which option is correct here?', 'options':[' A ', ' B ', ' C ', ' D '], 'correct_answer':' A '}
    result = QuestionService.validate(data,q)
    assert result['correct_answer'] == 'A' and result['options'] == ['A','B','C','D']


def test_legacy_padded_mcq_can_be_answered(service,repo):
    a = service.start(DEMO_ID)
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type']=='MCQ')
    q['options'] = [' '+x+' ' for x in q['options']]; q['correct_answer'] = ' '+q['correct_answer']+' '
    a['current_question_id'] = q['id']; a['question_override'] = q; repo.save_attempt(a)
    service.submit(a['id'],q['id'],q['correct_answer'])
    assert repo.list_responses(a['id'])[0]['evaluation']['score'] == 100


def test_catalog_normalizes_options(service):
    a = service.catalog.create_assessment({'title':'QA','job_title':'QA','description':'Testing','competencies':['QA']})
    q = service.catalog.create_question(a['id'],{'question_text':'Select the right option.', 'skill':'QA','question_type':'MCQ',
        'options':[' A ',' B '],'correct_answer':' A '})
    assert q['options'] == ['A','B'] and q['correct_answer'] == 'A'


def test_full_question_reaches_written_evaluator(service,repo,monkeypatch):
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type']=='Subjective')
    q['question_text'] = 'Long technical context. '*70 + 'Critical final requirement.'
    service.ai.client = object()
    fn = Mock(return_value={'correctness':0,'strengths':[],'weaknesses':[],'evidence':[],'feedback':'More evidence needed.'})
    monkeypatch.setattr(service.ai,'_json',fn)
    service.ai.evaluate_subjective(q,'answer')
    assert fn.call_args.args[0]['question'].endswith('Critical final requirement.')

def test_unicode_csrf_rejected_without_503(client):
    from conftest import csrf
    csrf(client)
    response = client.post(f'/assessment/{DEMO_ID}/start',data={'csrf_token':'गलत','candidate_name':'Test'})
    assert response.status_code == 400


def test_unicode_recruiter_password(app,client):
    from conftest import csrf
    app.config['RECRUITER_PASSWORD'] = 'पासवर्ड-🔑'
    response = client.post('/recruiter/login',data={'csrf_token':csrf(client),'password':'पासवर्ड-🔑'})
    assert response.status_code == 302 and client.get('/recruiter').status_code == 200


def test_assets_cache_but_candidate_data_does_not(client):
    assert 'max-age=3600' in client.get('/static/app.js').headers['Cache-Control']
    assert client.get('/').headers['Cache-Control'] == 'no-store'
    assert b'app.js?v=' in client.get('/').data


def test_persist_failure_leaves_lock_reusable(service,repo,monkeypatch):
    a,q = subjective_attempt(service,repo)
    original = repo.commit_answer
    monkeypatch.setattr(repo,'commit_answer',Mock(side_effect=RuntimeError('database unavailable')))
    with pytest.raises(RuntimeError): service.submit(a['id'],q['id'],best_answer(q))
    monkeypatch.setattr(repo,'commit_answer',original)
    assert service.submit(a['id'],q['id'],best_answer(q))['answered_count'] == 1

def test_different_candidates_can_process_concurrently(service,repo,monkeypatch):
    a,q = subjective_attempt(service,repo)
    b,r = subjective_attempt(service,repo)
    barrier = Barrier(2)
    original = service.ai.evaluate_subjective
    def grade(question,answer):
        barrier.wait(timeout=2)
        return original(question,answer)
    monkeypatch.setattr(service.ai,'evaluate_subjective',grade)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(service.submit,x['id'],question['id'],'technical answer') for x,question in [(a,q),(b,r)]]
        assert all(f.result()['answered_count']==1 for f in futures)
    assert not service._active_submissions

def test_generated_correct_answer_can_differ_only_in_outer_whitespace(repo):
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type']=='MCQ')
    data = {'question_text':'Which option is correct here?', 'options':[' A ', 'B', 'C', 'D'], 'correct_answer':'A'}
    assert QuestionService.validate(data,q)['correct_answer'] == 'A'
