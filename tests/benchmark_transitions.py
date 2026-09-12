"""Run controlled benchmarks, never live API calls. No extra dependencies.
python tests/benchmark_transitions.py [--source PATH] [--runs 3]
The optional source path permits an identical comparison against an extracted baseline.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--runs', type=int, default=3)
args = parser.parse_args()
if not 1 <= args.runs <= 10:
    parser.error('runs must be 1–10')
sys.path.insert(0,str(args.source.resolve()))
from app import create_app
from app.repositories.repository import InMemoryRepository
from app.services.ai_service import AIService
from app.seed import DEMO_ID


def run(full=False):
    ai = AIService(generate_questions=True)
    repo = InMemoryRepository()
    app = create_app({'TESTING':True,'DATABASE_MODE':'demo'},repo,ai)
    service = app.extensions['assessment_service']
    bank = repo.list_questions(DEMO_ID)
    counts = {'grade':0,'generate':0,'reads':0}
    for name in ('get_attempt','get_assessment','list_questions','list_responses'):
        original = getattr(repo,name)
        def read(*a,_fn=original,**kw):
            counts['reads'] += 1; time.sleep(.005)
            return _fn(*a,**kw)
        setattr(repo,name,read)
    def provider(payload,instructions,max_tokens=360):
        time.sleep(.10)
        if 'type' in payload:
            counts['generate'] += 1
            q = next(q for q in bank if q['skill']==payload['skill'] and q['difficulty']==payload['difficulty'])
            return {'question_text':q['question_text'], 'options':q['options'], 'correct_answer':q['correct_answer'],
                    'concepts':q['rubric'].get('concepts',[])[:5]}
        counts['grade'] += 1
        return {'correctness':1,'strengths':[],'weaknesses':[],'evidence':[payload['answer'][:15]],'feedback':'Clear technical evidence.'}
    ai._json = provider
    if not full:
        a = service.start(DEMO_ID)
        q = next(q for q in bank if q['question_type']=='Subjective')
        a['current_question_id'] = q['id']; repo.save_attempt(a)
    ai.client = object()
    counts.update(grade=0,generate=0,reads=0)
    start = time.perf_counter()
    if full:
        a = service.start(DEMO_ID)
        for _ in range(100):
            # Benchmark driver reads are excluded from the measured repository read delay.
            a = repo.tables['attempts'][a['id']]
            if a['status']=='completed': break
            q = a.get('question_override') or next(q for q in bank if q['id']==a['current_question_id'])
            answer = q['correct_answer'] if q['question_type']=='MCQ' else 'Explain the concept with a tested example and clear trade-offs.'
            service.submit(a['id'],q['id'],answer)
        else: raise AssertionError('Assessment did not terminate')
        questions = len(a['answered_ids'])
    else:
        service.submit(a['id'],q['id'],'Explain the concept with a tested example.')
        questions = 1
    return (time.perf_counter()-start)*1000,counts,questions

result={'provider':'simulated, no external calls','simulated_provider_delay_ms':100,
        'simulated_read_delay_ms':5,'runs':args.runs,'scenarios':{}}
for label,full in [('eligible_written_transition',False),('complete_assessment',True)]:
    runs=[run(full) for _ in range(args.runs)]
    result['scenarios'][label]={'median_ms':round(statistics.median(r[0] for r in runs),2),
        'questions':runs[0][2],'counts':runs[0][1]}
print(json.dumps(result,indent=2))
