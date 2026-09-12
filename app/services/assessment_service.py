from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
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
        question = None
        if attempt['current_question_id']:
            stored = next((q for q in self.repo.list_questions(assessment['id'])
                           if q['id'] == attempt['current_question_id']), None)
            if not stored:
                raise AppError('The current question is unavailable. Contact the assessment administrator.', 409)
            stored = attempt.get('question_override') or stored
            question = {k: stored[k] for k in ('id', 'question_text', 'skill', 'difficulty', 'question_type', 'options')}
        return {'id': attempt['id'], 'title': assessment['title'], 'status': attempt['status'],
                'answered_count': len(attempt['answered_ids']), 'max_questions': assessment['max_questions'],
                'progress': round(100 * len(attempt['answered_ids']) / assessment['max_questions']), 'question': question}

    def submit(self, attempt_id, question_id, answer):
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
        if question['question_type'] == 'MCQ':
            if answer not in question['options']:
                raise AppError('Select one of the provided options.')
            evaluation = self.ai.evaluate_mcq(question, answer)
        elif question['question_type'] == 'Subjective':
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
            previous_responses = self.repo.list_responses(attempt_id)
            seen = [r['evaluation'].get('question_snapshot', {}).get('question_text', '') for r in previous_responses]
            seen.append(question['question_text'])
            attempt['question_override'] = self.questions.prepare(next_question, question, answer, evaluation, seen)
        if reason:
            attempt.update(status='completed', termination_reason=reason, completed_at=now())
            responses = self.repo.list_responses(attempt_id) + [response]
            report = self._report(attempt, responses)
        self.repo.commit_answer(version, attempt, response, report)
        return self.public_attempt(attempt_id)

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
