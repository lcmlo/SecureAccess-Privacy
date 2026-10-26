import time

from .conftest import PASSWORD, csrf, post, signin
from .db_helpers import get_db


def test_registration_default_role_and_hash(app, client):
    csrf(client)
    response = post(
        client, "/register", {"username": "nova", "password": PASSWORD, "role": "admin"}
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
