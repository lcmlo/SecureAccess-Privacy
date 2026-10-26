import pytest

from app.extensions import db
from app.models import AuditLog, DeletionHistory, DeletionRequest, User
from app.services.audit_service import audit, now
from app.services.privacy_service import process_request
from app.utils.pseudonymization import user_ref

from .conftest import confirmation, post, seed, signin
from .db_helpers import get_db


def test_deletion_workflow(app, client):
    uid, secret = signin(client, app)
    data = confirmation(app, uid, secret)
    data["confirmation"] = "ELIMINAR"
    assert post(client, "/deletion", data).status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT * FROM deletion_requests").fetchone()
        rid = row["id"]
        assert row["user_id"] == uid and row["status"] == "pendente"
        assert (
            get_db()
            .execute("SELECT COUNT(*) FROM audit_logs WHERE event_type='pedido_eliminacao'")
            .fetchone()[0]
            == 1
        )
    data = confirmation(app, uid, secret)
    assert post(client, "/deletion", {**data, "confirmation": "ELIMINAR"}).status_code == 302
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM deletion_requests").fetchone()[0] == 1
    admin_client = app.test_client()
    aid, asecret = signin(admin_client, app, "administrador", "admin")
    path = f"/admin/deletions/{rid}"
    assert (
        post(
            admin_client,
            path,
            {**confirmation(app, aid, asecret), "action": "complete"},
        ).status_code
        == 409
    )
    assert (
        post(
            admin_client, path, {**confirmation(app, aid, asecret), "action": "process"}
        ).status_code
        == 302
    )
    assert (
        post(
            admin_client,
            path,
            {**confirmation(app, aid, asecret), "action": "complete"},
        ).status_code
        == 302
    )
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() is None
        assert (
            db.execute("SELECT * FROM audit_logs WHERE user_ref=?", (user_ref(uid),)).fetchone()
            is None
        )
        row = db.execute("SELECT * FROM deletion_requests").fetchone()
        assert row["status"] == "concluído" and row["user_id"] is None and row["completed_at"]
        assert (
            db.execute(
                "SELECT COUNT(*) FROM deletion_history WHERE request_id=?", (rid,)
            ).fetchone()[0]
            == 3
        )
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert client.get("/my-data").status_code == 302


def test_other_users_cannot_see_requests(app, client):
    uid, secret = signin(client, app)
    post(
        client,
        "/deletion",
        {**confirmation(app, uid, secret), "confirmation": "ELIMINAR"},
    )
    second = app.test_client()
    signin(second, app, "bob")
    assert "Ainda não apresentou".encode() in second.get("/deletion?user_id=1").data
    assert second.get("/export/1").status_code == 404


def test_failure_during_deletion_rolls_back_all_data(app, client, monkeypatch):
    uid, _ = seed(app)
    aid, secret = signin(client, app, "admin", "admin")
    with app.app_context():
        item = DeletionRequest(user_id=uid, requested_at=now(), status="em processamento")
        item.history.append(DeletionHistory(status="pendente", changed_at=now()))
        db.session.add(item)
        audit("login", user_ref(uid))
        db.session.commit()
        rid = item.id

    def fail_audit(*args, **kwargs):
        raise RuntimeError("Falha de escrita simulada")

    monkeypatch.setattr("app.services.privacy_service.audit", fail_audit)
    with app.app_context():
        with pytest.raises(RuntimeError):
            process_request(aid, rid, "complete")
        db.session.rollback()
        assert db.session.get(User, uid) is not None
        item = db.session.get(DeletionRequest, rid)
        assert (
            item.status == "em processamento" and item.completed_at is None and item.user_id == uid
        )
        assert (
            db.session.scalar(db.select(AuditLog).where(AuditLog.user_ref == user_ref(uid)))
            is not None
        )
