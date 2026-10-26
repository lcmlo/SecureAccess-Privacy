import pyotp
import pytest

from app.extensions import db

from .conftest import PASSWORD, confirmation, csrf, post, seed, signin
from .db_helpers import get_db


@pytest.mark.parametrize(
    "path",
    [
        "/admin/",
        "/admin/users",
        "/admin/logs",
        "/admin/deletions",
        "/admin/permissions",
        "/admin/settings",
    ],
)
def test_user_cannot_admin(app, client, path):
    signin(client, app)
    assert client.get(path).status_code == 403
    assert post(client, "/admin/users/1", {"action": "admin"}).status_code == 403


def test_admin_actions_revoke_sessions(app, client):
    aid, secret = signin(client, app, "administrador", "admin")
    target_client = app.test_client()
    uid, _ = signin(target_client, app, "bob")
    assert post(client, f"/admin/users/{aid}", {"action": "user"}).status_code == 403
    assert (
        post(
            client,
            f"/admin/users/{uid}",
            {**confirmation(app, aid, secret), "action": "deactivate"},
        ).status_code
        == 302
    )
    assert target_client.get("/dashboard").status_code == 302
    assert (
        post(
            client,
            f"/admin/users/{uid}",
            {**confirmation(app, aid, secret), "action": "activate"},
        ).status_code
        == 302
    )
    assert target_client.get("/dashboard").status_code == 302
    assert (
        post(
            client,
            f"/admin/users/{uid}",
            {**confirmation(app, aid, secret), "action": "admin"},
        ).status_code
        == 302
    )
    with app.app_context():
        assert (
            get_db().execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()[0] == "admin"
        )
    assert post(client, "/admin/settings", confirmation(app, aid, secret)).status_code == 302


def test_disabled_account_cannot_login_and_revoke_pending(app, client):
    uid, secret = seed(app)
    csrf(client)
    post(client, "/login", {"username": "alice", "password": PASSWORD})
    csrf(client, "/mfa")
    with app.app_context():
        get_db().execute("UPDATE users SET active=0 WHERE id=?", (uid,))
        get_db().commit()
        db.session.commit()
    assert post(client, "/mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    csrf(client)
    assert post(client, "/login", {"username": "alice", "password": PASSWORD}).status_code == 200
