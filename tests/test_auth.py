import time
import pyotp
from .conftest import PASSWORD, csrf, post, seed, signin
from secureaccess.db import get_db
from secureaccess.security import user_ref


def test_registration_default_role_and_hash(app, client):
    csrf(client)
    response = post(client, '/register', {'username': 'nova', 'password': PASSWORD, 'role': 'admin'})
    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute('SELECT * FROM users').fetchone()
        assert row['role'] == 'user' and row['password_hash'] != PASSWORD
        assert row['totp_secret'] is None
    assert post(client, '/register', {'username': 'outra', 'password': 'curta'}).status_code == 200


def test_invalid_login_and_pseudonym(app, client):
    uid, secret = seed(app)
    csrf(client)
    assert post(client, '/login', {'username': 'alice', 'password': 'errada'}).status_code == 200
    with app.app_context():
        row = get_db().execute('SELECT * FROM audit_logs').fetchone()
        assert row['user_ref'] == user_ref(uid) and row['result'] == 'falha'
        assert 'alice' not in str(dict(row)) and secret not in str(dict(row)) and PASSWORD not in str(dict(row))


def test_mfa_login_logout_and_replay(app, client):
    uid, secret = signin(client, app)
    assert client.get('/dashboard').status_code == 200
    assert client.get('/logout').status_code == 405
    assert post(client, '/logout').status_code == 302
    assert client.get('/dashboard').status_code == 302
    csrf(client)
    post(client, '/login', {'username': 'alice', 'password': PASSWORD})
    csrf(client, '/mfa')
    assert post(client, '/mfa', {'token': pyotp.TOTP(secret).now()}).status_code == 200
    with app.app_context():
        events = [r[0] for r in get_db().execute('SELECT event_type FROM audit_logs')]
        assert all(event in events for event in ['login', 'logout', 'mfa_falha'])


def test_setup_and_invalid_mfa(app, client):
    uid, secret = seed(app, enabled=False)
    csrf(client)
    assert post(client, '/login', {'username': 'alice', 'password': PASSWORD}).location.endswith('/setup-mfa')
    assert b'data:image/png;base64' in client.get('/setup-mfa').data
    assert post(client, '/setup-mfa', {'token': 'abcdef'}).status_code == 200
    assert post(client, '/setup-mfa', {'token': pyotp.TOTP(secret).now()}).status_code == 302
    with app.app_context():
        assert get_db().execute('SELECT mfa_enabled FROM users WHERE id=?', (uid,)).fetchone()[0] == 1
    # Não volta a expor uma configuração de MFA ativa.
    assert client.get('/setup-mfa').status_code == 302


def test_session_and_pending_expiry(app, client):
    signin(client, app)
    with client.session_transaction() as session:
        session['authenticated_at'] = time.time() - 1801
    assert client.get('/dashboard').status_code == 302
    with client.session_transaction() as session:
        session['pending_user_id'] = 1
        session['pending_at'] = time.time() - 301
    assert client.get('/mfa').location.endswith('/login')


def test_csrf_headers_throttle(app, client):
    assert client.post('/register', data={'username': 'teste', 'password': PASSWORD}).status_code == 400
    app.config['AUTH_MAX_ATTEMPTS'] = 2
    csrf(client)
    for _ in range(2):
        assert post(client, '/login', {'username': 'naoexiste', 'password': 'errada'}).status_code == 200
    assert post(client, '/login', {'username': 'naoexiste', 'password': 'errada'}).status_code == 429
    response = client.get('/login')
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'frame-ancestors' in response.headers['Content-Security-Policy']
