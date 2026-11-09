from app.extensions import db
from app.utils.pseudonymization import user_ref

from .conftest import PASSWORD, confirmation, csrf, post, seed, signin
from .db_helpers import get_db
import time
from types import SimpleNamespace
from unittest.mock import patch

import pyotp

def test_invalid_login_and_pseudonym(app, client):
    uid, secret = seed(app)
    csrf(client)
    assert post(client, "/login", {"username": "alice", "password": "errada"}).status_code == 200
    with app.app_context():
        row = get_db().execute("SELECT * FROM audit_logs").fetchone()
        assert row["user_ref"] == user_ref(uid) and row["result"] == "falha"
        assert (
            "alice" not in str(dict(row))
            and secret not in str(dict(row))
            and PASSWORD not in str(dict(row))
        )


def test_admin_logs_no_direct_identifier_and_self_deletion_blocked(app, client):
    aid, secret = signin(client, app, "administrador", "admin")
    other, _ = seed(app, "NomeDiretoNaoMostrar")
    from app.services.audit_service import audit

    with app.app_context():
        audit("login", user_ref(other))
        get_db().commit()
        db.session.commit()
    assert b"NomeDiretoNaoMostrar" not in client.get("/admin/logs").data
    assert (
        post(
            client,
            "/deletion",
            {**confirmation(app, aid, secret), "confirmation": "ELIMINAR"},
        ).status_code
        == 302
    )
    assert (
        post(
            client,
            "/admin/deletions/1",
            {**confirmation(app, aid, secret), "action": "process"},
        ).status_code
        == 403
    )
    # Utilizar um intervalo TOTP futuro simulado apenas neste teste.
    fixed_time = int(time.time()) + 90
    token = pyotp.TOTP(secret).at(fixed_time)

    with patch(
            "app.services.mfa_service.time",
            SimpleNamespace(time=lambda: fixed_time),
    ):
        response = post(
            client,
            "/admin/users/999",
            {
                "password": PASSWORD,
                "token": token,
                "action": "deactivate",
            },
        )

    assert response.status_code == 404
