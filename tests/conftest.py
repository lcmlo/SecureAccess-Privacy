import time
import pytest
import pyotp
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash
from secureaccess import create_app
from secureaccess.db import get_db, migrate

PASSWORD = 'Uma-palavra-passe-segura!'


@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 's' * 48, 'AUDIT_HMAC_KEY': 'a' * 48,
                      'MFA_ENC_KEY': Fernet.generate_key().decode(), 'DATABASE': str(tmp_path / 'test.db'),
                      'AUTH_MAX_ATTEMPTS': 100})
    with app.app_context():
        migrate(get_db())
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path='/login'):
    response = client.get(path)
    assert response.status_code in (200, 302)
    with client.session_transaction() as session:
        return session.get('csrf_token')


def post(client, path, data=None):
    with client.session_transaction() as session:
        token = session.get('csrf_token')
    if not token:
        token = csrf(client)
    return client.post(path, data={'csrf_token': token, **(data or {})})


def seed(app, username='alice', role='user', enabled=True):
    secret = pyotp.random_base32()
    with app.app_context():
        db = get_db()
        encrypted = app.extensions['fernet'].encrypt(secret.encode()).decode()
        uid = db.execute('INSERT INTO users(username,password_hash,totp_secret,mfa_enabled,role) VALUES(?,?,?,?,?)',
                         (username, generate_password_hash(PASSWORD), encrypted, int(enabled), role)).lastrowid
        db.commit()
    return uid, secret


def signin(client, app, username='alice', role='user'):
    uid, secret = seed(app, username, role)
    csrf(client)
    response = post(client, '/login', {'username': username, 'password': PASSWORD})
    assert response.status_code == 302
    csrf(client, '/mfa')
    response = post(client, '/mfa', {'token': pyotp.TOTP(secret).now()})
    assert response.status_code == 302
    return uid, secret


def confirmation(app, uid, secret):
    # Simula ter aguardado o intervalo seguinte sem fazer os testes esperar 30 s.
    with app.app_context():
        get_db().execute('UPDATE users SET last_totp_step=NULL WHERE id=?', (uid,))
        get_db().commit()
    return {'password': PASSWORD, 'token': pyotp.TOTP(secret).now()}
