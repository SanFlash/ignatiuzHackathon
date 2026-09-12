import hmac
from functools import wraps
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from app.errors import AppError

bp = Blueprint('web', __name__)


def catalog(): return current_app.extensions['catalog']
def service(): return current_app.extensions['assessment_service']


def recruiter_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if current_app.config['RECRUITER_PASSWORD'] and not session.get('recruiter'):
            return redirect(url_for('web.login'))
        return fn(*args, **kwargs)
    return wrapped


def attempt_access(attempt_id):
    service().get_attempt(attempt_id)
    if attempt_id not in session.get('attempts', []) and not session.get('recruiter'):
        raise AppError('Open this attempt in the browser where you started it.', 403)


@bp.get('/')
def home(): return render_template('index.html', assessments=catalog().list_assessments())


@bp.route('/recruiter/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        expected = current_app.config['RECRUITER_PASSWORD']
        if not expected or hmac.compare_digest(request.form.get('password', ''), expected):
            session['recruiter'] = True
            return redirect(url_for('web.recruiter'))
        raise AppError('Invalid recruiter password.', 403)
    return render_template('login.html')


@bp.post('/recruiter/logout')
def logout():
    session.pop('recruiter', None)
    return redirect(url_for('web.home'))


@bp.get('/recruiter')
@recruiter_required
def recruiter():
    session['recruiter'] = True
    return render_template('recruiter.html', dashboard=catalog().dashboard())


@bp.route('/recruiter/assessments/new', methods=['GET', 'POST'])
@recruiter_required
def create_assessment():
    if request.method == 'POST':
        assessment = catalog().create_assessment(request.form)
        return redirect(url_for('web.questions', assessment_id=assessment['id']))
    return render_template('create_assessment.html')


@bp.route('/recruiter/assessments/<assessment_id>/questions', methods=['GET', 'POST'])
@recruiter_required
def questions(assessment_id):
    if request.method == 'POST':
        catalog().create_question(assessment_id, request.form)
        return redirect(url_for('web.questions', assessment_id=assessment_id))
    assessment = catalog().assessment(assessment_id)
    locked = any(a['assessment_id'] == assessment_id for a in catalog().dashboard()['attempts'])
    return render_template('questions.html', assessment=assessment,
                           questions=catalog().list_questions(assessment_id), locked=locked)


@bp.route('/assessment/<assessment_id>/start', methods=['GET', 'POST'])
def start(assessment_id):
    assessment = catalog().assessment(assessment_id)
    if request.method == 'POST':
        attempt = service().start(assessment_id, request.form.get('candidate_name', ''))
        session['attempts'] = (session.get('attempts', []) + [attempt['id']])[-30:]
        return redirect(url_for('web.assessment', attempt_id=attempt['id']))
    return render_template('start.html', assessment=assessment)


@bp.get('/assessment/<attempt_id>')
def assessment(attempt_id):
    attempt_access(attempt_id)
    public = service().public_attempt(attempt_id)
    if public['status'] == 'completed':
        return redirect(url_for('web.report', attempt_id=attempt_id))
    return render_template('assessment.html', attempt=public, candidate_mode=True)


@bp.post('/assessment/<attempt_id>/answer')
def answer(attempt_id):
    attempt_access(attempt_id)
    data = request.get_json(silent=True) if request.is_json else request.form
    if not isinstance(data, dict) and not hasattr(data, 'get'):
        raise AppError('Submit a valid answer object.')
    result = service().submit(attempt_id, data.get('question_id'), data.get('answer'))
    if request.is_json:
        return jsonify(result)
    return redirect(url_for('web.report' if result['status'] == 'completed' else 'web.assessment', attempt_id=attempt_id))


@bp.get('/report/<attempt_id>')
def report(attempt_id):
    attempt_access(attempt_id)
    return render_template('report.html', report=service().report(attempt_id), attempt=service().get_attempt(attempt_id))


@bp.get('/api/attempt/<attempt_id>')
def api_attempt(attempt_id):
    attempt_access(attempt_id)
    return jsonify(service().public_attempt(attempt_id))
