import re

import pyotp
import pytest
from cryptography.fernet import Fernet
from flask import g
from flask_migrate import upgrade
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User

PASSWORD = "Uma-palavra-passe-segura!"


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "s" * 48,
            "AUDIT_HMAC_KEY": "a" * 48,
            "MFA_ENC_KEY": Fernet.generate_key().decode(),
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "test.db").as_posix(),
            "AUTH_MAX_ATTEMPTS": 100,
        }
    )

    @application.teardown_appcontext
    def close_inspection(error=None):
        conn = g.pop("inspection_db", None)
        if conn is not None:
            conn.close()

    with application.app_context():
        upgrade()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path="/login"):
    response = client.get(path, follow_redirects=True)
    assert response.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    return match.group(1)


def post(client, path, data=None):
    # Flask-WTF exige o token assinado do formulário, não o valor bruto do cookie.
    token = csrf(client, "/my-data" if path == "/logout" else "/login")
    return client.post(path, data={"csrf_token": token, **(data or {})})


def seed(app, username="alice", role="user", enabled=True):
    secret = pyotp.random_base32()
    with app.app_context():
        encrypted = app.extensions["fernet"].encrypt(secret.encode()).decode()
        user = User(
            username=username,
            password_hash=generate_password_hash(PASSWORD),
            totp_secret=encrypted,
            mfa_enabled=int(enabled),
            role=role,
        )
        db.session.add(user)
        db.session.commit()
        uid = user.id
    return uid, secret


def signin(client, app, username="alice", role="user"):
    uid, secret = seed(app, username, role)
    response = post(client, "/login", {"username": username, "password": PASSWORD})
    assert response.status_code == 302
    response = post(client, "/mfa", {"token": pyotp.TOTP(secret).now()})
    assert response.status_code == 302
    return uid, secret


def confirmation(app, uid, secret):
    # Simula o próximo intervalo sem fazer a suite esperar 30 segundos por operação.
    with app.app_context():
        user = db.session.get(User, uid)
        user.last_totp_step = None
        db.session.commit()
    return {"password": PASSWORD, "token": pyotp.TOTP(secret).now()}
