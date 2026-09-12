import hmac
import logging
import os
import secrets
import hashlib
from flask import Flask, jsonify, render_template, request, session
from pathlib import Path
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException
from app.errors import AppError
from app.repositories.repository import InMemoryRepository
from app.services.ai_service import AIService
from app.services.catalog_service import CatalogService
from app.services.assessment_service import AssessmentService


def create_app(config=None, repository=None, ai_service=None):
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    app = Flask(__name__)
    assets = Path(app.static_folder)
    asset_version = hashlib.sha256((assets / 'style.css').read_bytes() + (assets / 'app.js').read_bytes()).hexdigest()[:12]
    configured_secret = os.getenv('SECRET_KEY', '')
    app.config.update(SECRET_KEY=configured_secret if configured_secret and configured_secret != 'change-me' else secrets.token_hex(32),
                      DATABASE_MODE=os.getenv('DATABASE_MODE', 'demo').strip().lower(),
                      SUPABASE_URL=os.getenv('SUPABASE_URL', '').strip(), SUPABASE_KEY=os.getenv('SUPABASE_KEY', ''),
                      RECRUITER_PASSWORD=os.getenv('RECRUITER_PASSWORD', ''), MAX_CONTENT_LENGTH=65536,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '').lower() == 'true',
                      CSRF_ENABLED=True, SEED_DEMO=True)
    if config:
        app.config.update(config)
    logging.basicConfig(level=logging.INFO)
    if app.config['DATABASE_MODE'] not in ('auto', 'demo', 'supabase'):
        raise RuntimeError('DATABASE_MODE must be demo, supabase or auto.')
    if repository is None and app.config['DATABASE_MODE'] == 'demo':
        repository = InMemoryRepository()
    if repository is None:
        if app.config['DATABASE_MODE'] == 'supabase' and not app.config['SUPABASE_URL']:
            raise RuntimeError('Supabase mode requires SUPABASE_URL and SUPABASE_KEY.')
        if bool(app.config['SUPABASE_URL']) != bool(app.config['SUPABASE_KEY']):
            raise RuntimeError('Configure both SUPABASE_URL and SUPABASE_KEY, or leave both empty for demo mode.')
        if app.config['SUPABASE_URL']:
            from app.repositories.supabase_repository import SupabaseRepository
            repository = SupabaseRepository(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
        else:
            repository = InMemoryRepository()
    # One credential, one fixed provider. Ignore legacy OpenRouter/base-URL settings.
    ai = ai_service or AIService(os.getenv('OPENAI_API_KEY', '').strip(),
                                 os.getenv('OPENAI_MODEL', '').strip(), generate_questions=True)
    app.extensions['repo'] = repository
    app.extensions['ai'] = ai
    app.extensions['catalog'] = CatalogService(repository)
    app.extensions['assessment_service'] = AssessmentService(repository, ai)
    # Never silently seed or overwrite a remote database at web-server startup.
    if repository.demo and app.config['SEED_DEMO']:
        from app.seed import seed_demo
        seed_demo(repository)

    @app.cli.command('seed-demo')
    def seed_demo_command():
        """Seed an empty demo assessment in the selected repository."""
        from app.seed import seed_demo
        print('Demo assessment:', seed_demo(repository))

    @app.cli.command('doctor')
    def doctor():
        import click
        from app.diagnostics import log_failure
        click.echo('Database: ' + ('demo (memory)' if repository.demo else 'Supabase'))
        click.echo('AI: ' + ai.status)
        try:
            assessments = repository.list_assessments()
            click.echo(f'Database read OK: {len(assessments)} assessments')
            if not repository.demo and assessments:
                # Select the new column explicitly to catch an old schema without mutating it.
                repository.client.table('attempts').select('id,question_override').limit(1).execute()
            if not assessments:
                click.echo('Run: python -m flask --app run:app seed-demo')
        except Exception as exc:
            ref, code, message = log_failure(app.logger, exc, database=True)
            raise click.ClickException(f'{code}: {message} Reference: {ref}') from None

    @app.before_request
    def csrf_protection():
        session.setdefault('csrf_token', secrets.token_urlsafe(32))
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and app.config['CSRF_ENABLED']:
            supplied = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
            if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode('utf-8'), session['csrf_token'].encode('utf-8')):
                raise AppError('Your form expired. Reload the page and try again.', 400)

    @app.context_processor
    def context():
        return {'demo_mode': repository.demo, 'ai_status': ai.status, 'asset_version': asset_version,
                'recruiter_open': not app.config['RECRUITER_PASSWORD'], 'csrf_token': session.get('csrf_token', '')}

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'public, max-age=3600' if request.endpoint == 'static' else 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        return response

    def error_response(message, status):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(error=message), status
        return render_template('error.html', message=message, status=status), status

    @app.errorhandler(AppError)
    def application_error(exc): return error_response(exc.message, exc.status)

    @app.errorhandler(HTTPException)
    def http_error(exc): return error_response(exc.name, exc.code)

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        from app.diagnostics import log_failure
        database_error = not repository.demo and type(exc).__module__.startswith(('postgrest', 'httpx', 'httpcore', 'supabase'))
        reference, code, message = log_failure(app.logger, exc, database=database_error)
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(error=message, code=code, reference=reference), 503
        return render_template('error.html', message=message, status=503, code=code, reference=reference), 503

    from app.routes import bp
    app.register_blueprint(bp)
    return app
