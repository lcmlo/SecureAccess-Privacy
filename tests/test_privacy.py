import csv
import io
import json

import pytest

from app.extensions import db
from app.extensions import db as orm_db
from app.services.audit_service import audit
from app.services.retention_service import cleanup
from app.utils.pseudonymization import user_ref

from .conftest import confirmation, post, seed, signin
from .db_helpers import get_db


def test_own_data_and_filters(app, client):
    uid, _ = signin(client, app)
    other, _ = seed(app, "outra")
    with app.app_context():
        audit("exportacao", user_ref(other))
        audit("mfa_falha", user_ref(uid), "falha")
        get_db().commit()
        db.session.commit()
    response = client.get("/my-data?user_id=" + str(other))
    assert b"alice" in response.data and b"outra" not in response.data
    response = client.get("/history?event_type=exportacao")
    assert "Não existem registos".encode() in response.data
    response = client.get("/history?event_type=mfa_falha&result=falha")
    assert "Falha na MFA".encode() in response.data
    assert client.get("/history?start=invalid").status_code == 400
    assert client.get("/history?result=anything").status_code == 400
    assert client.get("/history?start=2000-01-01&end=2000-01-02").status_code == 200
    assert b"/admin/" not in client.get("/dashboard").data


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_export_safety_and_ownership(app, client, fmt):
    uid, secret = signin(client, app)
    seed(app, "outra")
    data = confirmation(app, uid, secret)
    data.update(
        {
            "categories": ["account", "history", "requests"],
            "format": fmt,
            "user_id": 999,
        }
    )
    response = post(client, "/export", data)
    assert response.status_code == 200 and "attachment" in response.headers["Content-Disposition"]
    body = response.get_data(as_text=True)
    for forbidden in [
        "password_hash",
        "totp_secret",
        "session_version",
        "last_totp_step",
        secret,
        "outra",
    ]:
        assert forbidden not in body
    if fmt == "json":
        assert json.loads(body)["account"]["id"] == uid
    else:
        rows = list(csv.reader(io.StringIO(body.lstrip("\ufeff"))))
        assert rows[0] == ["categoria", "registo", "campo", "valor"]
        assert any(r[-1] == "alice" for r in rows)
    with app.app_context():
        assert (
            get_db()
            .execute(
                "SELECT COUNT(*) FROM audit_logs WHERE user_ref=? AND event_type='exportacao'",
                (user_ref(uid),),
            )
            .fetchone()[0]
            == 1
        )


def test_sensitive_confirmation_and_export_categories(app, client):
    uid, secret = signin(client, app)
    assert (
        post(
            client,
            "/export",
            {
                "categories": ["account"],
                "format": "json",
                "password": "errada",
                "token": "000000",
            },
        ).status_code
        == 403
    )
    assert post(client, "/export", {"categories": ["secrets"], "format": "json"}).status_code == 400
    assert post(client, "/deletion", {"confirmation": "nao"}).status_code == 400


def test_retention(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO audit_logs(user_ref,event_type,event_timestamp,result) VALUES('ref','login','2000-01-01 00:00:00','sucesso')"
        )
        db.commit()
        audit("login", "recent-ref")
        orm_db.session.commit()
        rid = db.execute(
            "INSERT INTO deletion_requests(requested_at,status,completed_at) VALUES('2000-01-01','concluído','2000-01-02')"
        ).lastrowid
        db.execute(
            "INSERT INTO deletion_history(request_id,status,changed_at) VALUES(?,'concluído','2000-01-02')",
            (rid,),
        )
        db.execute(
            "INSERT INTO deletion_requests(requested_at,status) VALUES('2000-01-01','pendente')"
        )
        db.commit()
        assert cleanup() == (1, 1)
        assert db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM deletion_history").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM deletion_requests").fetchone()[0] == 1
