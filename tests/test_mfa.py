import pyotp

from app.utils.pseudonymization import user_ref

from .conftest import PASSWORD, csrf, post, seed, signin
from .db_helpers import get_db


def test_mfa_login_logout_and_replay(app, client):
    uid, secret = signin(client, app)
    assert client.get("/dashboard").status_code == 200
    assert client.get("/logout").status_code == 405
    assert post(client, "/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302
    csrf(client)
    post(client, "/login", {"username": "alice", "password": PASSWORD})
    csrf(client, "/mfa")
    assert post(client, "/mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 200
    with app.app_context():
        events = [r[0] for r in get_db().execute("SELECT event_type FROM audit_logs")]
        assert all(event in events for event in ["login", "logout", "mfa_falha"])


def test_setup_and_invalid_mfa(app, client):
    uid, secret = seed(app, enabled=False)
    csrf(client)
    assert post(client, "/login", {"username": "alice", "password": PASSWORD}).location.endswith(
        "/setup-mfa"
    )
    assert b"data:image/png;base64" in client.get("/setup-mfa").data
    assert post(client, "/setup-mfa", {"token": "abcdef"}).status_code == 200
    assert post(client, "/setup-mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    with app.app_context():
        assert (
            get_db().execute("SELECT mfa_enabled FROM users WHERE id=?", (uid,)).fetchone()[0] == 1
        )
    # Não volta a expor uma configuração de MFA ativa.
    assert client.get("/setup-mfa").status_code == 302


def test_mfa_invalid_and_counter_survives_new_session(app, client):
    uid, secret = seed(app)
    csrf(client)
    post(client, "/login", {"username": "alice", "password": PASSWORD})
    csrf(client, "/mfa")
    assert post(client, "/mfa", {"token": "abcdef"}).status_code == 200
    with app.app_context():
        row = get_db().execute("SELECT * FROM audit_logs").fetchone()
        assert row["event_type"] == "mfa_falha" and row["user_ref"] == user_ref(uid)
    app.config["AUTH_MAX_ATTEMPTS"] = 1
    another = app.test_client()
    csrf(another)
    assert post(another, "/login", {"username": "alice", "password": "errada"}).status_code == 429


def test_atomic_totp_replay_and_csrf_for_sensitive_endpoints(app, client):
    uid, secret = signin(client, app)
    token = pyotp.TOTP(secret).now()
    assert (
        post(
            client,
            "/export",
            {
                "categories": ["account"],
                "format": "json",
                "password": PASSWORD,
                "token": token,
            },
        ).status_code
        == 403
    )
    for path in [
        "/export",
        "/deletion",
        "/logout",
        "/admin/settings",
        "/admin/users/2",
    ]:
        assert client.post(path).status_code == 400
