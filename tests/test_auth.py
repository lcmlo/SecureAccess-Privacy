import time

from .conftest import PASSWORD, csrf, post, signin
from .db_helpers import get_db


def test_registration_default_role_and_hash(app, client):
    csrf(client)
    response = post(
        client, "/register", {"username": "nova", "email": "nova@example.com", "password": PASSWORD, "password_confirmation": PASSWORD, "role": "admin"}
    )
    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT * FROM users").fetchone()
        assert row["role"] == "user" and row["password_hash"] != PASSWORD
        assert row["totp_secret"] is None
    assert post(client, "/register", {"username": "outra", "password": "curta"}).status_code == 200


def test_session_and_pending_expiry(app, client):
    signin(client, app)
    with client.session_transaction() as session:
        session["authenticated_at"] = time.time() - 1801
    assert client.get("/dashboard").status_code == 302
    with client.session_transaction() as session:
        session["pending_user_id"] = 1
        session["pending_at"] = time.time() - 301
    assert client.get("/mfa").location.endswith("/login")


def test_csrf_headers_throttle(app, client):
    assert (
        client.post("/register", data={"username": "teste", "password": PASSWORD}).status_code
        == 400
    )
    app.config["AUTH_MAX_ATTEMPTS"] = 2
    csrf(client)
    for _ in range(2):
        assert (
            post(client, "/login", {"username": "naoexiste", "password": "errada"}).status_code
            == 200
        )
    assert (
        post(client, "/login", {"username": "naoexiste", "password": "errada"}).status_code == 429
    )
    response = client.get("/login")
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors" in response.headers["Content-Security-Policy"]


def test_successful_passwords_do_not_consume_failure_limit(app, client):
    """Mesmo muitos logins corretos não esgotam o limite de 2 falhas."""
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User, UserProfile

    app.config["AUTH_MAX_ATTEMPTS"] = 2
    app.config["AUTH_ORIGIN_MAX_REQUESTS"] = 30
    with app.app_context():
        user = User(
            username="utilizador_teste_rate",
            password_hash=generate_password_hash(PASSWORD),
            role="user",
        )
        user.profile = UserProfile()
        db.session.add(user)
        db.session.commit()

    for _ in range(6):
        csrf(client)
        response = post(
            client, "/login", {"username": "utilizador_teste_rate", "password": PASSWORD}
        )
        assert response.status_code == 302  # MFA pendente, sem aumentar falhas

    for _ in range(2):
        csrf(client)
        response = post(
            client, "/login", {"username": "utilizador_teste_rate", "password": "incorreta"}
        )
        assert response.status_code == 200

    csrf(client)
    assert post(
        client, "/login", {"username": "utilizador_teste_rate", "password": PASSWORD}
    ).status_code == 429  # Só após duas falhas; password correta não ignora bloqueio


def test_origin_limit_counts_even_successful_passwords(app, client):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User, UserProfile

    app.config["AUTH_MAX_ATTEMPTS"] = 5
    app.config["AUTH_ORIGIN_MAX_REQUESTS"] = 3
    with app.app_context():
        user = User(
            username="origem_teste_rate",
            password_hash=generate_password_hash(PASSWORD),
            role="user",
        )
        user.profile = UserProfile()
        db.session.add(user)
        db.session.commit()

    for _ in range(3):
        csrf(client)
        assert post(
            client, "/login", {"username": "origem_teste_rate", "password": PASSWORD}
        ).status_code == 302
    csrf(client)
    assert post(
        client, "/login", {"username": "origem_teste_rate", "password": PASSWORD}
    ).status_code == 429


def test_failure_counters_shared_by_login_mfa_and_confirmation(app):
    """O contador de falhas usa a conta, não um bucket diferente por fase."""
    import pytest
    from werkzeug.exceptions import TooManyRequests

    from app.services import auth_service

    app.config["AUTH_MAX_ATTEMPTS"] = 2
    with app.app_context():
        account = "user:999997"
        auth_service._record_failure(account)
        auth_service._record_failure(account)
        with pytest.raises(TooManyRequests):
            auth_service._check_failure_limit(account)
        auth_service._clear_failures(account)
        from app.extensions import db

        db.session.commit()
        auth_service._check_failure_limit(account)
