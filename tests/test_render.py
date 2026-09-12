import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest
from app import create_app
from app.repositories.repository import InMemoryRepository
from app.services.ai_service import AIService


def test_health_has_no_cookie_or_dependency_calls(client, repo, app, monkeypatch):
    blocked = Mock(side_effect=AssertionError('Health must not call external services'))
    monkeypatch.setattr(repo, 'list_assessments', blocked)
    monkeypatch.setattr(app.extensions['ai'], 'evaluate_subjective', blocked)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {'status': 'ok'}
    assert 'Set-Cookie' not in response.headers
    assert response.headers['Cache-Control'] == 'no-store'
    blocked.assert_not_called()


@pytest.mark.parametrize('secret,password,missing', [('', 'pw', 'SECRET_KEY'), ('change-me', 'pw', 'SECRET_KEY'), ('stable', '', 'RECRUITER_PASSWORD')])
def test_render_rejects_missing_production_credentials(monkeypatch, secret, password, missing):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('SECRET_KEY', secret)
    monkeypatch.setenv('RECRUITER_PASSWORD', password)
    with pytest.raises(RuntimeError, match=missing):
        create_app(repository=InMemoryRepository(), ai_service=AIService())


def test_render_https_cookie_and_protected_recruiter(monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('SECRET_KEY', 'stable-test-secret')
    monkeypatch.setenv('RECRUITER_PASSWORD', 'test-password')
    monkeypatch.delenv('COOKIE_SECURE', raising=False)
    app = create_app(repository=InMemoryRepository(), ai_service=AIService())
    client = app.test_client()
    response = client.get('/', base_url='https://example.onrender.com')
    assert 'Secure;' in response.headers['Set-Cookie']
    assert 'HttpOnly;' in response.headers['Set-Cookie']
    response = client.get('/recruiter', base_url='https://example.onrender.com')
    assert response.status_code == 302
    assert response.location.endswith('/recruiter/login')


def test_gunicorn_uses_render_port_and_shared_demo_process(monkeypatch):
    monkeypatch.setenv('PORT', '14567')
    config = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'gunicorn.conf.py'))
    assert config['bind'] == '0.0.0.0:14567'
    assert config['workers'] == 1
    assert config['threads'] > 1
    assert config['max_requests'] == 0
