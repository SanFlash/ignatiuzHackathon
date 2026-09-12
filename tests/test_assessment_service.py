from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from app.errors import AppError, Conflict
from app.seed import DEMO_ID, SKILLS
from conftest import best_answer, complete

def test_start_public_data(service):
    a = service.start(DEMO_ID, 'Candidate')
    assert a['status'] == 'active' and a['version'] == 0
    public = service.public_attempt(a['id'])
    assert public['answered_count'] == 0
    assert not {'skill_state', 'candidate_name', 'version'} & public.keys()
    assert not {'correct_answer', 'rubric', 'points'} & public['question'].keys()

@pytest.mark.parametrize('kind', ['MCQ', 'Subjective'])
def test_submit_types(service, repo, kind):
    a = service.start(DEMO_ID)
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type'] == kind)
    a['current_question_id'] = q['id']; repo.save_attempt(a)
    public = service.submit(a['id'], q['id'], best_answer(q))
    updated = service.get_attempt(a['id'])
    assert public['answered_count'] == 1 and public['progress'] > 0
    s = updated['skill_state'][q['skill']]
    assert s['evidence_count'] == 1 and s['confidence'] > .15 and s['estimated_level'] != 2.5
    assert len(repo.list_responses(a['id'])) == 1

def test_completion_and_report(service, repo):
    a = service.start(DEMO_ID); seen = complete(service, repo, a['id']); report = service.report(a['id'])
    assert 10 <= len(seen) <= 15 and len(set(seen)) == len(seen)
    assert report['coverage'] == 100 and 0 <= report['overall_score'] <= 100
    assert len(report['interview_questions']) == len(SKILLS)
    assert report['evidence'] and report['strengths']
    assert all(s['evidence_count'] >= 2 for s in report['skill_state'].values())
    with pytest.raises(AppError, match='already completed'): service.submit(a['id'], seen[-1], 'anything')

@pytest.mark.parametrize('answer', ['', '   ', None, [], 'x'*20001])
def test_invalid_answer_no_mutation(service, repo, answer):
    a = service.start(DEMO_ID)
    with pytest.raises(AppError): service.submit(a['id'], a['current_question_id'], answer)
    assert service.get_attempt(a['id'])['version'] == 0 and not repo.list_responses(a['id'])

def test_duplicate_wrong_question(service, repo):
    a = service.start(DEMO_ID); q = next(q for q in repo.list_questions(DEMO_ID) if q['id'] == a['current_question_id'])
    with pytest.raises(Conflict): service.submit(a['id'], str(uuid4()), 'anything')
    service.submit(a['id'], q['id'], best_answer(q))
    with pytest.raises(Conflict): service.submit(a['id'], q['id'], best_answer(q))
    assert len(repo.list_responses(a['id'])) == 1

def test_failure_preserves_state(service, repo, monkeypatch):
    a = service.start(DEMO_ID); q = next(q for q in repo.list_questions(DEMO_ID) if q['id'] == a['current_question_id'])
    def fail(*args): raise RuntimeError('database down')
    monkeypatch.setattr(repo, 'commit_answer', fail)
    with pytest.raises(RuntimeError): service.submit(a['id'], q['id'], best_answer(q))
    assert service.get_attempt(a['id']) == a and repo.list_responses(a['id']) == []

def test_concurrent_submit_across_service_instances(service, repo, monkeypatch):
    a = service.start(DEMO_ID); q = next(q for q in repo.list_questions(DEMO_ID) if q['id'] == a['current_question_id'])
    from app.services.assessment_service import AssessmentService
    workers = [service, AssessmentService(repo, service.ai)]
    original = repo.commit_answer; barrier = Barrier(2)
    def synchronized(*args):
        barrier.wait(timeout=5)
        return original(*args)
    monkeypatch.setattr(repo, 'commit_answer', synchronized)
    def submit(_):
        try:
            workers[_].submit(a['id'], q['id'], best_answer(q)); return 'saved'
        except Conflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as executor: results = list(executor.map(submit, range(2)))
    assert sorted(results) == ['conflict', 'saved']
    assert service.get_attempt(a['id'])['version'] == 1 and len(repo.list_responses(a['id'])) == 1

def test_pool_exhaustion_report(service, repo):
    a = service.start(DEMO_ID)
    keep = {next(q['id'] for q in repo.list_questions(DEMO_ID) if q['skill'] == s) for s in SKILLS}
    keep.add(a['current_question_id'])
    repo.tables['questions'] = {k: q for k, q in repo.tables['questions'].items() if k in keep}
    complete(service, repo, a['id'])
    assert service.report(a['id'])['termination_reason'] == 'question_pool_exhausted'

def test_catalog_validation_lock(service, repo):
    with pytest.raises(AppError): service.start(str(uuid4()))
    with pytest.raises(AppError): service.start(DEMO_ID, '')
    a = service.catalog.create_assessment({'title':'QA','job_title':'Tester','description':'Checks',
          'competencies':['Testing'],'max_questions':4,'confidence_target':.7})
    with pytest.raises(AppError, match='no available questions'): service.start(a['id'])
    q = {'skill':'Testing','question_type':'MCQ','difficulty':1,'points':1,
         'question_text':'Choose A','options':['A','B'],'correct_answer':'A'}
    service.catalog.create_question(a['id'],q); service.start(a['id'])
    with pytest.raises(AppError, match='locked'): service.catalog.create_question(a['id'],q)

def test_no_early_report(service):
    a = service.start(DEMO_ID)
    with pytest.raises(AppError, match='complete'): service.report(a['id'])

def test_paths_differ_for_strong_and_struggling_candidates(service,repo):
    paths = []
    for strong in (True,False):
        a = service.start(DEMO_ID); path = []
        while a['status'] == 'active':
            q = next(q for q in repo.list_questions(DEMO_ID) if q['id'] == a['current_question_id'])
            path.append((q['skill'],q['difficulty'],q['id']))
            if strong: answer = best_answer(q)
            elif q['question_type'] == 'MCQ': answer = next(o for o in q['options'] if o != q['correct_answer'])
            else: answer = 'I do not know.'
            service.submit(a['id'],q['id'],answer); a = service.get_attempt(a['id'])
        paths.append(path)
    assert paths[0] != paths[1]
    assert sum(q[1] for q in paths[0]) > sum(q[1] for q in paths[1])

def test_maximum_count(service,repo):
    assessment = repo.get_assessment(DEMO_ID); assessment['max_questions'] = 5; repo.create_assessment(assessment)
    a = service.start(DEMO_ID); assert len(complete(service,repo,a['id'])) == 5
    assert service.report(a['id'])['termination_reason'] == 'maximum_questions'

def test_candidate_identity(service,repo):
    a = service.start(DEMO_ID,'Test candidate')
    assert repo.tables['users'][a['candidate_id']]['name'] == 'Test candidate'

def test_invalid_mcq_option(service,repo):
    a = service.start(DEMO_ID)
    q = next(q for q in repo.list_questions(DEMO_ID) if q['question_type'] == 'MCQ')
    a['current_question_id'] = q['id']; repo.save_attempt(a)
    with pytest.raises(AppError,match='provided options'): service.submit(a['id'],q['id'],'Invented option')
    assert repo.get_attempt(a['id'])['version'] == 0

def test_missing_question(service,repo):
    a = service.start(DEMO_ID); del repo.tables['questions'][a['current_question_id']]
    with pytest.raises(AppError,match='unavailable'): service.public_attempt(a['id'])
    with pytest.raises(AppError,match='Question not found'): service.submit(a['id'],a['current_question_id'],'answer')

def test_uncovered_competencies_block_start(service,repo):
    repo.tables['questions'] = {k:q for k,q in repo.tables['questions'].items() if q['skill'] != 'SQL'}
    with pytest.raises(AppError,match='every competency'): service.start(DEMO_ID)

def test_seed_retries_partial_bank_without_duplicates(repo):
    from app.seed import seed_demo
    question = repo.list_questions(DEMO_ID)[0]
    del repo.tables['questions'][question['id']]
    seed_demo(repo)
    assert len(repo.list_questions(DEMO_ID)) == 25
    seed_demo(repo)
    assert len(repo.list_questions(DEMO_ID)) == 25
