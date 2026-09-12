from app.errors import Conflict


class SupabaseRepository:
    demo = False

    def __init__(self, url: str, key: str):
        from supabase import create_client
        self.client = create_client(url, key)

    def _put(self, table, data, conflict='id'):
        result = self.client.table(table).upsert(data, on_conflict=conflict).execute()
        return result.data[0]

    def _get(self, table, column, value):
        rows = self.client.table(table).select('*').eq(column, value).limit(1).execute().data
        return rows[0] if rows else None

    def _list(self, table, column=None, value=None):
        # PostgREST defaults to a row cap. Page explicitly rather than silently truncating.
        result, offset = [], 0
        while True:
            query = self.client.table(table).select('*').order('id')
            if column:
                query = query.eq(column, value)
            rows = query.range(offset, offset + 499).execute().data
            result.extend(rows)
            if len(rows) < 500:
                return result
            offset += 500

    def create_assessment(self, data):
        return self.client.rpc('create_catalog_assessment', {'p_assessment': data}).execute().data
    def get_assessment(self, assessment_id): return self._get('assessments', 'id', assessment_id)
    def list_assessments(self): return self._list('assessments')
    def create_question(self, data): return self._put('questions', data)
    def list_questions(self, assessment_id): return self._list('questions', 'assessment_id', assessment_id)
    def create_attempt(self, data):
        return self.client.rpc('create_candidate_attempt', {'p_attempt': data}).execute().data
    def get_attempt(self, attempt_id): return self._get('attempts', 'id', attempt_id)
    def list_attempts(self): return self._list('attempts')
    def save_attempt(self, data): return self._put('attempts', data)
    def save_response(self, data): return self._put('responses', data, 'attempt_id,question_id')
    def list_responses(self, attempt_id): return self._list('responses', 'attempt_id', attempt_id)
    def save_report(self, data): return self._put('candidate_reports', data, 'attempt_id')
    def get_report(self, attempt_id): return self._get('candidate_reports', 'attempt_id', attempt_id)

    def commit_answer(self, previous_version, attempt, response, report):
        try:
            self.client.rpc('commit_assessment_answer', {
                'p_version': previous_version, 'p_attempt': attempt,
                'p_response': response, 'p_report': report,
            }).execute()
        except Exception as exc:
            if 'attempt_conflict' in str(exc):
                raise Conflict() from exc
            raise
