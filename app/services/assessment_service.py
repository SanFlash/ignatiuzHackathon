from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from app.errors import AppError, Conflict
from app.services.catalog_service import CatalogService, identifier
from app.services.adaptive_engine import AdaptiveEngine
from app.services.question_service import QuestionService


def now(): return datetime.now(timezone.utc).isoformat()


class AssessmentService:
    def __init__(self, repo, ai):
        self.repo, self.ai = repo, ai
        self.catalog = CatalogService(repo)
        self.engine = AdaptiveEngine()
        self.questions = QuestionService(ai)
        # Active IDs are removed in finally; unrelated attempts never block each other.
        self._submission_guard = Lock()
        self._active_submissions = set()

    def get_attempt(self, attempt_id):
        attempt = self.repo.get_attempt(identifier(attempt_id))
        if not attempt:
            raise AppError('Attempt not found.', 404)
        return attempt

    def start(self, assessment_id, candidate_name='Demo candidate'):
        assessment = self.catalog.assessment(assessment_id)
        if not isinstance(candidate_name, str) or not candidate_name.strip() or len(candidate_name) > 120:
            raise AppError('Enter a candidate name of 1–120 characters.')
        pool = self.repo.list_questions(assessment_id)
        playable = [q for q in pool if q['question_type'] != 'Coding']
        if not playable:
            raise AppError('This assessment has no available questions. Ask the recruiter to add questions.', 409)
        if set(assessment['competencies']) - {q['skill'] for q in playable}:
            raise AppError('Add at least one supported question for every competency before starting.', 409)
        state = self.engine.initial_state(assessment['competencies'])
        question = self.engine.select_question(playable, state, [], assessment['priorities'])
        override = self.questions.prepare(question)
        return self.repo.create_attempt({'question_override': override, 'id': str(uuid4()), 'assessment_id': assessment_id,
                'candidate_name': candidate_name.strip(), 'status': 'active', 'skill_state': state,
                'answered_ids': [], 'current_question_id': question['id'], 'version': 0,
                'started_at': now(), 'completed_at': None, 'termination_reason': None})

    def public_attempt(self, attempt_id):
        attempt = self.get_attempt(attempt_id)
        assessment = self.catalog.assessment(attempt['assessment_id'])
        pool = None
        if attempt['current_question_id'] and not attempt.get('question_override'):
            pool = self.repo.list_questions(assessment['id'])
        return self._public(attempt, assessment, pool)

    @staticmethod
    def _public(attempt, assessment, pool=None):
        question = None
        if attempt['current_question_id']:
            stored = attempt.get('question_override') or next(
                (q for q in (pool or []) if q['id'] == attempt['current_question_id']), None)
            if not stored:
                raise AppError('The current question is unavailable. Contact the assessment administrator.', 409)
            question = {k: stored[k] for k in ('id', 'question_text', 'skill', 'difficulty', 'question_type', 'options')}
        return {'id': attempt['id'], 'title': assessment['title'], 'status': attempt['status'],
                'answered_count': len(attempt['answered_ids']), 'max_questions': assessment['max_questions'],
                'progress': 100 if attempt['status'] == 'completed' else round(
                    100 * len(attempt['answered_ids']) / assessment['max_questions']), 'question': question}

    def _independent_next(self, assessment, attempt, question, pool):
        """Prove next selection cannot depend on the current pending grade.

        Evidence counts/confidence do not depend on correctness. If the current
        skill is excluded by the hard coverage guard, only unchanged skill
        estimates can participate in the next ranking. No speculative grading.
        """
        state = self.engine.update(attempt['skill_state'], question['skill'], {'observed_level': 2.5})
        answered = attempt['answered_ids'] + [question['id']]
        ranked = self.engine.rank_questions(pool, state, answered, assessment['priorities'])
        if not ranked or any(q['skill'] == question['skill'] for _, q in ranked):
            return None
        if self.engine.termination(assessment, state, len(answered), bool(ranked)):
            return None
        return ranked[0][1]

    def submit(self, attempt_id, question_id, answer):
        canonical_id = identifier(attempt_id)
        with self._submission_guard:
            if canonical_id in self._active_submissions:
                raise Conflict('A submission is already processing. Check progress before trying again.')
            self._active_submissions.add(canonical_id)
        try:
            return self._submit(canonical_id, question_id, answer)
        finally:
            with self._submission_guard:
                self._active_submissions.discard(canonical_id)

    def _submit(self, attempt_id, question_id, answer):
        attempt = self.get_attempt(attempt_id)
        if attempt['status'] == 'completed':
            raise AppError('This assessment is already completed.', 409)
        if question_id != attempt['current_question_id'] or question_id in attempt['answered_ids']:
            raise Conflict()
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 3000:
            raise AppError('Enter an answer of 1–3,000 characters.')
        answer = answer.strip()
        assessment = self.catalog.assessment(attempt['assessment_id'])
        pool = self.repo.list_questions(assessment['id'])
        question = next((q for q in pool if q['id'] == question_id), None)
        if not question:
            raise AppError('Question not found.', 404)
        question = attempt.get('question_override') or question
        previous_responses = None
        parallel_question = None
        prepared_override = None
        if question['question_type'] == 'MCQ':
            # Normalize legacy padded options without making answer keys public.
            question['options'] = [option.strip() for option in question['options']]
            question['correct_answer'] = question['correct_answer'].strip()
            if answer not in question['options']:
                raise AppError('Select one of the provided options.')
            evaluation = self.ai.evaluate_mcq(question, answer)
        elif question['question_type'] == 'Subjective':
            if self.ai.client and self.ai.generate_questions and not self.ai.local_evaluation:
                parallel_question = self._independent_next(assessment, attempt, question, pool)
            if parallel_question:
                previous_responses = self.repo.list_responses(attempt_id)
                seen = self._seen_questions(previous_responses, question)
                # Both calls use the submitted answer. Generation does not receive
                # an invented grade; server selection was proven independent above.
                with ThreadPoolExecutor(max_workers=2, thread_name_prefix='assessment-ai') as executor:
                    future = executor.submit(self.questions.prepare, parallel_question, question, answer, None, seen)
                    evaluation = self.ai.evaluate_subjective(question, answer)
                    prepared_override = future.result()
            else:
                evaluation = self.ai.evaluate_subjective(question, answer)
        else:
            raise AppError('Coding execution is a future extension.', 409)
        evaluation['question_snapshot'] = deepcopy(question)
        version = attempt['version']
        attempt['skill_state'] = self.engine.update(attempt['skill_state'], question['skill'], evaluation)
        attempt['answered_ids'].append(question_id)
        next_question = self.engine.select_question(pool, attempt['skill_state'], attempt['answered_ids'], assessment['priorities'])
        reason = self.engine.termination(assessment, attempt['skill_state'], len(attempt['answered_ids']), bool(next_question))
        attempt.update(version=version + 1, current_question_id=None if reason else next_question['id'])
        response = {'id': str(uuid4()), 'attempt_id': attempt_id, 'question_id': question_id,
                    'answer': answer, 'evaluation': evaluation, 'skill': question['skill'],
                    'points': question['points'], 'created_at': now()}
        report = None
        attempt['question_override'] = None
        if not reason and self.ai.generate_questions:
            if parallel_question and parallel_question['id'] == next_question['id']:
                attempt['question_override'] = prepared_override
            elif not parallel_question:
                if previous_responses is None:
                    previous_responses = self.repo.list_responses(attempt_id)
                seen = self._seen_questions(previous_responses, question)
                attempt['question_override'] = self.questions.prepare(next_question, question, answer, evaluation, seen)
            # Defensive mismatch: use the engine-selected bank item, never a wrong
            # speculative item or an extra paid retry.
        if reason:
            attempt.update(status='completed', termination_reason=reason, completed_at=now())
            responses = (previous_responses if previous_responses is not None else
                         self.repo.list_responses(attempt_id)) + [response]
            report = self._report(attempt, responses)
        self.repo.commit_answer(version, attempt, response, report)
        return self._public(attempt, assessment, pool)

    @staticmethod
    def _seen_questions(responses, question):
        return [r['evaluation'].get('question_snapshot', {}).get('question_text', '') for r in responses] + [question['question_text']]

    def _report(self, attempt, responses):
        state = deepcopy(attempt['skill_state'])
        weighted = sum(r['evaluation']['score'] * r['points'] for r in responses)
        weight = sum(r['points'] for r in responses)
        strengths, gaps, evidence = [], [], []
        for skill, item in state.items():
            if not item['evidence_count']:
                gaps.append(f'{skill}: not assessed; no skill conclusion available.')
            elif item['estimated_level'] < 3:
                gaps.append(f'{skill}: limited evidence; explore fundamentals in an interview.')
            elif item['estimated_level'] >= 3.5:
                strengths.append(f'{skill}: demonstrated evidence at level {item["estimated_level"]:.1f}.')
        for response in responses:
            evaluation = response['evaluation']
            evidence.append({'skill': response['skill'], 'question_id': response['question_id'],
                             'source': evaluation['source'], 'score': evaluation['score'],
                             'question_text': evaluation.get('question_snapshot', {}).get('question_text', ''),
                             'evidence': evaluation['evidence'], 'feedback': evaluation['feedback']})
            strengths.extend(f'{response["skill"]}: {s}' for s in evaluation['strengths'])
            gaps.extend(f'{response["skill"]}: {s}' for s in evaluation['weaknesses'])
        return {'id': str(uuid4()), 'attempt_id': attempt['id'], 'overall_score': round(weighted / weight, 1) if weight else 0,
                'skill_state': state, 'coverage': round(100 * sum(s['evidence_count'] > 0 for s in state.values()) / len(state)),
                'strengths': list(dict.fromkeys(strengths)), 'gaps': list(dict.fromkeys(gaps)), 'evidence': evidence,
                'interview_questions': self.ai.interview_questions(state), 'created_at': now(),
                'termination_reason': attempt['termination_reason'], 'answered_count': len(responses)}

    def report(self, attempt_id):
        attempt = self.get_attempt(attempt_id)
        if attempt['status'] != 'completed':
            raise AppError('The report will be available when the assessment is complete.', 409)
        report = self.repo.get_report(attempt_id)
        if not report:
            raise AppError('Report is temporarily unavailable.', 503)
        return report
