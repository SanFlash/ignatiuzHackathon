"""One bounded OpenAI call per new question; grading/selection stay server-owned."""
from copy import deepcopy
import logging
import re
from time import monotonic

log = logging.getLogger(__name__)


def normalized(text):
    return re.sub(r'\W+', ' ', text.casefold()).strip()


class QuestionService:
    def __init__(self, ai):
        self.ai = ai
        self.retry_after = 0.0
        self.last_status = 'bank'

    def prepare(self, selected, previous=None, answer='', evaluation=None, seen=None):
        if not selected or not self.ai.generate_questions or not self.ai.client or monotonic() < self.retry_after:
            return None
        seen = seen or []
        # Hard character bounds cap context even for very long candidate answers.
        context = {'skill': selected['skill'], 'difficulty': selected['difficulty'],
                   'type': selected['question_type'], 'reference': selected['question_text'][:250],
                   'avoid': [q[:160] for q in seen[-5:]]}
        if previous:
            context['last'] = {'skill': previous['skill'], 'question': previous['question_text'][:200],
                'answer': answer[:800]}
            if evaluation is not None:
                context['last'].update(score=evaluation['score'],
                    gaps=[s[:100] for s in evaluation['weaknesses'][:3]])
        try:
            data = self.ai._json(context,
                'Create one NEW technical question at the given skill, difficulty and type. '
                'Use last answer/gaps to choose a useful follow-up when relevant. Do not repeat avoid questions. '
                'JSON: question_text (under 500 chars), options (4 strings for MCQ, else []), '
                'correct_answer (exact MCQ option, else null), concepts (3-5 short rubric terms for written answers, else []). '
                'No explanations. Ensure one unambiguously correct MCQ answer.', max_tokens=360)
            result = self.validate(data, selected)
            if normalized(result['question_text']) in {normalized(q) for q in seen}:
                raise ValueError('Repeated question')
            self.last_status = 'openai'
            result['origin'] = self.last_status
            return result
        except Exception:
            # No retry storm when the key, model, credits or provider is unavailable.
            self.retry_after = monotonic() + 60
            self.last_status = 'bank_fallback'
            log.warning('Question generation unavailable/invalid; bank fallback active for 60 seconds.')
            return None

    @staticmethod
    def validate(data, selected):
        if not isinstance(data, dict):
            raise ValueError('Expected question object')
        prompt = data.get('question_text')
        if not isinstance(prompt, str) or not 15 <= len(prompt.strip()) <= 500:
            raise ValueError('Invalid question text')
        result = deepcopy(selected)
        result['question_text'] = prompt.strip()
        if selected['question_type'] == 'MCQ':
            options = data.get('options')
            if (not isinstance(options, list) or len(options) != 4
                    or any(not isinstance(x, str) or not x.strip() or len(x) > 200 for x in options)
                    or len({x.strip().casefold() for x in options}) != 4
                    or not isinstance(data.get('correct_answer'), str)
                    or data['correct_answer'].strip() not in [x.strip() for x in options]):
                raise ValueError('Invalid MCQ')
            result.update(options=[x.strip() for x in options], correct_answer=data['correct_answer'].strip(), rubric={})
        elif selected['question_type'] == 'Subjective':
            concepts = data.get('concepts')
            if (not isinstance(concepts, list) or not 3 <= len(concepts) <= 5
                    or any(not isinstance(x, str) or not x.strip(' |') or len(x) > 100 for x in concepts)):
                raise ValueError('Invalid rubric')
            concepts = ['|'.join(alias.strip() for alias in term.split('|') if alias.strip()) for term in concepts]
            if any(not term for term in concepts) or len(set(concepts)) != len(concepts):
                raise ValueError('Empty or duplicate rubric concept')
            result.update(options=[], correct_answer=None, rubric={'concepts': concepts, 'min_words': 40})
        else:
            raise ValueError('Unsupported question type')
        # Identity, skill, difficulty, type and points come exclusively from the selected bank item.
        return result
