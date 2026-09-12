from app.services.adaptive_engine import AdaptiveEngine

def pool():
    return [{'id': f'{skill}{level}', 'skill': skill, 'difficulty': level, 'question_type': 'MCQ'}
            for skill in ('Python', 'SQL') for level in range(1, 6)]

def test_initial_state():
    assert AdaptiveEngine.initial_state(['Python']) == {'Python': {'estimated_level': 2.5, 'confidence': .15, 'evidence_count': 0}}

def test_selection_deterministic_and_medium():
    e = AdaptiveEngine(); state = e.initial_state(['Python', 'SQL'])
    q = e.select_question(pool(), state, [])
    assert q['difficulty'] in (2, 3)
    assert e.select_question(list(reversed(pool())), state, []) == q

def test_no_repetition_or_coding():
    e = AdaptiveEngine(); state = e.initial_state(['Python', 'SQL'])
    questions = pool() + [{'id': 'code', 'skill': 'Python', 'difficulty': 2, 'question_type': 'Coding'}]
    seen = []
    while (q := e.select_question(questions, state, seen)):
        assert q['id'] not in seen and q['id'] != 'code'
        seen.append(q['id'])
    assert len(seen) == 10

def test_skill_confidence_update_immutable():
    state = AdaptiveEngine.initial_state(['Python'])
    updated = AdaptiveEngine.update(state, 'Python', {'observed_level': 4})
    assert state['Python']['estimated_level'] == 2.5
    assert updated['Python'] == {'estimated_level': 3.1, 'confidence': .405, 'evidence_count': 1}

def test_difficulty_adaptation():
    e = AdaptiveEngine(); state = e.initial_state(['Python', 'SQL'])
    strong = e.update(state, 'Python', {'observed_level': 5})
    weak = e.update(state, 'Python', {'observed_level': 1})
    questions = [q for q in pool() if q['skill'] == 'Python']
    assert e.select_question(questions, strong, [])['difficulty'] > e.select_question(questions, weak, [])['difficulty']

def test_coverage():
    e = AdaptiveEngine(); state = e.initial_state(['Python', 'SQL'])
    state['Python']['evidence_count'] = 2
    assert e.select_question(pool(), state, [])['skill'] == 'SQL'

def test_exhaustion():
    assert AdaptiveEngine().select_question([], {}, []) is None

def test_bounds():
    state = AdaptiveEngine.initial_state(['Python'])
    for _ in range(100): state = AdaptiveEngine.update(state, 'Python', {'observed_level': 5})
    assert 1 <= state['Python']['estimated_level'] <= 5
    assert state['Python']['confidence'] <= .95

def test_termination():
    a = {'max_questions': 20, 'confidence_target': .3}
    e = AdaptiveEngine(); state = e.initial_state(['Python', 'SQL'])
    assert e.termination(a, state, 1, True) is None
    for skill in state:
        for _ in range(2): state = e.update(state, skill, {'observed_level': 4})
    assert e.termination(a, state, 3, True) is None
    assert e.termination(a, state, 4, True) == 'confidence_reached'
    assert e.termination(a, state, 20, True) == 'maximum_questions'
    assert e.termination(a, e.initial_state(['Python']), 1, False) == 'question_pool_exhausted'
