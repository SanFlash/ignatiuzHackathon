from uuid import uuid4, UUID
from app.errors import AppError


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise AppError('The requested item was not found.', 404) from None


def text_field(data, name, maximum=200):
    value = data.get(name, '')
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise AppError(f'{name.replace("_", " ").capitalize()} is required (maximum {maximum} characters).')
    return value.strip()


class CatalogService:
    def __init__(self, repo):
        self.repo = repo

    def assessment(self, assessment_id):
        result = self.repo.get_assessment(identifier(assessment_id))
        if not result:
            raise AppError('Assessment not found.', 404)
        return result

    def list_assessments(self): return self.repo.list_assessments()
    def list_questions(self, assessment_id):
        self.assessment(assessment_id)
        return self.repo.list_questions(assessment_id)

    def create_assessment(self, data):
        title = text_field(data, 'title', 160)
        job_title = text_field(data, 'job_title', 160)
        description = text_field(data, 'description', 4000)
        skills = data.get('competencies', [])
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(',') if s.strip()]
        if (not isinstance(skills, list) or not 1 <= len(skills) <= 12
                or any(not isinstance(s, str) or not s.strip() or len(s) > 80 for s in skills)):
            raise AppError('Provide 1–12 competencies, separated by commas.')
        skills = list(dict.fromkeys(s.strip() for s in skills))
        try:
            maximum = int(data.get('max_questions', 12))
            target = float(data.get('confidence_target', .70))
        except (TypeError, ValueError, OverflowError):
            raise AppError('Invalid question limit or confidence target.') from None
        if not max(4, len(skills)) <= maximum <= 100 or not .3 <= target <= .95:
            raise AppError('Question limit must be 4–100 and cover all competencies. Confidence must be 0.30–0.95.')
        return self.repo.create_assessment({'id': str(uuid4()), 'title': title, 'job_title': job_title,
                    'description': description, 'max_questions': maximum, 'confidence_target': target,
                    'competencies': skills, 'priorities': {s: 1 for s in skills}})

    def create_question(self, assessment_id, data):
        assessment = self.assessment(assessment_id)
        if any(a['assessment_id'] == assessment_id for a in self.repo.list_attempts()):
            raise AppError('This question bank is locked because attempts exist. Create a new assessment version.', 409)
        skill = text_field(data, 'skill', 80)
        if skill not in assessment['competencies']:
            raise AppError('Select a competency belonging to this assessment.')
        kind = data.get('question_type')
        if kind not in ('MCQ', 'Subjective', 'Coding'):
            raise AppError('Invalid question type.')
        try:
            difficulty, points = int(data.get('difficulty', 3)), float(data.get('points', 1))
        except (ValueError, TypeError, OverflowError):
            raise AppError('Invalid difficulty or points.') from None
        if difficulty not in range(1, 6) or not 0 < points <= 100:
            raise AppError('Difficulty must be 1–5; points must be greater than 0 and at most 100.')
        options = data.get('options', [])
        if isinstance(options, str):
            options = [x.strip() for x in options.splitlines() if x.strip()]
        if isinstance(options, list) and all(isinstance(x, str) for x in options):
            options = [x.strip() for x in options]
        correct = data.get('correct_answer', '')
        if isinstance(correct, str):
            correct = correct.strip()
        if kind == 'MCQ' and (not isinstance(options, list) or not 2 <= len(options) <= 8
                or any(not isinstance(x, str) or not x or len(x) > 1000 for x in options)
                or len(set(options)) != len(options) or correct not in options):
            raise AppError('MCQs need 2–8 unique options and an exact matching correct answer.')
        rubric = data.get('rubric', {})
        if isinstance(rubric, str):
            rubric = {'concepts': [x.strip() for x in rubric.split(',') if x.strip()], 'min_words': 40}
        if kind != 'MCQ':
            if not isinstance(rubric, dict):
                raise AppError('Provide a rubric with concepts.')
            concepts = rubric.get('concepts', [])
            if (not isinstance(concepts, list) or not 1 <= len(concepts) <= 20
                    or any(not isinstance(x, str) or not x.strip(' |') or len(x) > 160 for x in concepts)):
                raise AppError('Provide 1–20 rubric concepts, separated by commas. Use | for synonyms.')
            try:
                words = int(rubric.get('min_words', 40))
            except (ValueError, TypeError):
                raise AppError('Invalid rubric minimum word count.') from None
            if not 1 <= words <= 1000:
                raise AppError('Rubric minimum words must be 1–1000.')
            rubric = {'concepts': concepts, 'min_words': words}
        else:
            rubric = {}
        return self.repo.create_question({'id': str(uuid4()), 'assessment_id': assessment_id,
                 'question_text': text_field(data, 'question_text', 6000), 'skill': skill,
                 'difficulty': difficulty, 'question_type': kind, 'points': points,
                 'options': options if kind == 'MCQ' else [],
                 'correct_answer': correct if kind == 'MCQ' else None, 'rubric': rubric})

    def dashboard(self):
        assessments, attempts = self.repo.list_assessments(), self.repo.list_attempts()
        completed = sum(a['status'] == 'completed' for a in attempts)
        active_ids = {a['assessment_id'] for a in attempts if a['status'] == 'active'}
        return {'assessments': assessments, 'attempts': attempts, 'total': len(assessments),
                'active': len(active_ids), 'candidate_count': len(attempts), 'completed': completed}
