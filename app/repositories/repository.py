"""Persistence boundary. Multi-row answer writes must use commit_answer."""
from copy import deepcopy
from threading import RLock
from uuid import uuid4
from typing import Protocol
from app.errors import Conflict


class Repository(Protocol):
    demo: bool
    def create_assessment(self, data: dict) -> dict: ...
    def get_assessment(self, assessment_id: str) -> dict | None: ...
    def list_assessments(self) -> list[dict]: ...
    def create_question(self, data: dict) -> dict: ...
    def list_questions(self, assessment_id: str) -> list[dict]: ...
    def create_attempt(self, data: dict) -> dict: ...
    def get_attempt(self, attempt_id: str) -> dict | None: ...
    def list_attempts(self) -> list[dict]: ...
    def save_attempt(self, data: dict) -> dict: ...
    def save_response(self, data: dict) -> dict: ...
    def list_responses(self, attempt_id: str) -> list[dict]: ...
    def save_report(self, data: dict) -> dict: ...
    def get_report(self, attempt_id: str) -> dict | None: ...
    def commit_answer(self, previous_version: int, attempt: dict, response: dict, report: dict | None) -> None: ...


class InMemoryRepository:
    demo = True

    def __init__(self):
        self.tables = {t: {} for t in ('users', 'assessments', 'questions', 'attempts', 'responses', 'candidate_reports')}
        self.lock = RLock()

    def _put(self, table, data, key=None):
        with self.lock:
            self.tables[table][key or data['id']] = deepcopy(data)
            return deepcopy(data)

    def _get(self, table, key):
        with self.lock:
            return deepcopy(self.tables[table].get(key))

    def _list(self, table, column=None, value=None):
        with self.lock:
            return deepcopy([r for r in self.tables[table].values() if column is None or r[column] == value])

    def create_assessment(self, data): return self._put('assessments', data)
    def get_assessment(self, assessment_id): return self._get('assessments', assessment_id)
    def list_assessments(self): return self._list('assessments')
    def create_question(self, data): return self._put('questions', data)
    def list_questions(self, assessment_id): return self._list('questions', 'assessment_id', assessment_id)
    def create_attempt(self, data):
        with self.lock:
            data = deepcopy(data)
            candidate_id = str(uuid4())
            self._put('users', {'id': candidate_id, 'name': data['candidate_name'], 'role': 'candidate'})
            data['candidate_id'] = candidate_id
            return self._put('attempts', data)
    def get_attempt(self, attempt_id): return self._get('attempts', attempt_id)
    def list_attempts(self): return self._list('attempts')
    def save_attempt(self, data): return self._put('attempts', data)
    def save_response(self, data): return self._put('responses', data, (data['attempt_id'], data['question_id']))
    def list_responses(self, attempt_id): return self._list('responses', 'attempt_id', attempt_id)
    def save_report(self, data): return self._put('candidate_reports', data, data['attempt_id'])
    def get_report(self, attempt_id): return self._get('candidate_reports', attempt_id)

    def commit_answer(self, previous_version, attempt, response, report):
        with self.lock:
            current = self.get_attempt(attempt['id'])
            if (not current or current['version'] != previous_version or current['status'] != 'active'
                    or current['current_question_id'] != response['question_id']
                    or (attempt['id'], response['question_id']) in self.tables['responses']):
                raise Conflict()
            self.save_response(response)
            self.save_attempt(attempt)
            if report:
                self.save_report(report)
