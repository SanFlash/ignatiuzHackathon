import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.services.ai_service import AIService
from app.seed import DEMO_ID

@pytest.fixture
def question(repo): return next(q for q in repo.list_questions(DEMO_ID) if q['question_type'] == 'Subjective')

def test_local_scoring(question):
    ai = AIService()
    irrelevant = ai.evaluate_subjective(question,'I am a great employee. '*100)
    relevant = ai.evaluate_subjective(question,' '.join(c.split('|')[0] for c in question['rubric']['concepts']))
    assert irrelevant['score'] == 0 and relevant['score'] > irrelevant['score']
    assert relevant['source'] == 'local_rubric' and relevant['evidence']

@pytest.mark.parametrize('bad',[None,{'correctness':10},{'correctness':float('nan')},{'correctness':True},
 {'correctness':.8,'strengths':[],'weaknesses':[],'evidence':['invented quote'],'feedback':'ok'}])
def test_invalid_llm_fallback(question,bad):
    ai = AIService(); ai.client = object(); ai._json = Mock(return_value=bad)
    assert ai.evaluate_subjective(question,'Use None to create a fresh default list.')['source'] == 'local_rubric'

def test_timeout_fallback(question):
    ai = AIService(); ai.client = object(); ai._json = Mock(side_effect=TimeoutError())
    assert ai.evaluate_subjective(question,'technical answer')['source'] == 'local_rubric'
    prompts = ai.interview_questions({'Python':{'estimated_level':4,'evidence_count':3,'confidence':.7}})
    assert prompts[0]['skill'] == 'Python' and 'scale' in prompts[0]['question']

def test_valid_llm_schema(question):
    ai = AIService(); ai.client = object()
    ai._json = Mock(return_value={'correctness':.8,'strengths':['Explains None'],'weaknesses':[],
                                 'evidence':['None'],'feedback':'Demonstrates the concept.'})
    result = ai.evaluate_subjective(question,'Use None instead.')
    assert result['source'] == 'llm' and result['score'] == 80 and 1 <= result['observed_level'] <= 5

def test_sdk_shape_no_network(question):
    ai = AIService()
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
       'correctness':.5,'strengths':[],'weaknesses':[],'evidence':['None'],'feedback':'Partial evidence.'})))])
    create = Mock(return_value=response)
    ai.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert ai.evaluate_subjective(question,'None')['source'] == 'llm'
    payload = create.call_args.kwargs
    assert payload['response_format'] == {'type':'json_object'}
    assert 'untrusted' in payload['messages'][0]['content']
