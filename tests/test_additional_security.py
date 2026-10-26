import time
import pyotp
from .conftest import seed, signin, csrf, post, confirmation, PASSWORD
from secureaccess.db import get_db
from secureaccess.security import user_ref


def test_mfa_invalid_and_counter_survives_new_session(app, client):
    uid, secret = seed(app)
    csrf(client)
    post(client, '/login', {'username': 'alice', 'password': PASSWORD})
    csrf(client, '/mfa')
    assert post(client, '/mfa', {'token': 'abcdef'}).status_code == 200
    with app.app_context():
        row = get_db().execute('SELECT * FROM audit_logs').fetchone()
        assert row['event_type'] == 'mfa_falha' and row['user_ref'] == user_ref(uid)
    app.config['AUTH_MAX_ATTEMPTS'] = 1
    another = app.test_client()
    csrf(another)
    assert post(another, '/login', {'username': 'alice', 'password': 'errada'}).status_code == 429


def test_disabled_account_cannot_login_and_revoke_pending(app, client):
    uid, secret = seed(app)
    csrf(client)
    post(client, '/login', {'username': 'alice', 'password': PASSWORD})
    csrf(client, '/mfa')
    with app.app_context():
        get_db().execute('UPDATE users SET active=0 WHERE id=?', (uid,))
        get_db().commit()
    assert post(client, '/mfa', {'token': pyotp.TOTP(secret).now()}).status_code == 302
    csrf(client)
    assert post(client, '/login', {'username': 'alice', 'password': PASSWORD}).status_code == 200


def test_no_sensitive_fields_in_any_user_page(app, client):
    uid, secret = signin(client, app)
    for path in ['/dashboard', '/my-data', '/history', '/privacy', '/export', '/deletion']:
        response = client.get(path)
        assert response.status_code == 200
        assert secret.encode() not in response.data
        assert b'password_hash' not in response.data and b'/admin/' not in response.data


def test_admin_logs_no_direct_identifier_and_self_deletion_blocked(app, client):
    aid, secret = signin(client, app, 'administrador', 'admin')
    other, _ = seed(app, 'NomeDiretoNaoMostrar')
    from secureaccess.security import audit
    with app.app_context():
        audit('login', user_ref(other))
        get_db().commit()
    assert b'NomeDiretoNaoMostrar' not in client.get('/admin/logs').data
    assert post(client, '/deletion', {**confirmation(app, aid, secret), 'confirmation': 'ELIMINAR'}).status_code == 302
    assert post(client, '/admin/deletions/1', {**confirmation(app, aid, secret), 'action': 'process'}).status_code == 403
    assert post(client, '/admin/users/999', {**confirmation(app, aid, secret), 'action': 'deactivate'}).status_code == 404


def test_atomic_totp_replay_and_csrf_for_sensitive_endpoints(app, client):
    uid, secret = signin(client, app)
    token = pyotp.TOTP(secret).now()
    assert post(client, '/export', {'categories': ['account'], 'format': 'json', 'password': PASSWORD, 'token': token}).status_code == 403
    for path in ['/export', '/deletion', '/logout', '/admin/settings', '/admin/users/2']:
        assert client.post(path).status_code == 400


def test_sql_injection_and_escaping(app, client):
    aid, _ = signin(client, app, 'administrador', 'admin')
    assert client.get('/admin/users?q=%27%20OR%201=1--').status_code == 200
    assert 'Não foram encontradas'.encode() in client.get('/admin/users?q=%27%20OR%201=1--').data
    with app.app_context():
        get_db().execute('INSERT INTO users(username,password_hash) VALUES(?,?)', ('<script>alert(1)</script>', 'legacy'))
        get_db().commit()
    response = client.get('/admin/users')
    assert b'<script>alert(1)</script>' not in response.data
    assert b'&lt;script&gt;' in response.data
