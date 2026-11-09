import json

import pyotp
import pytest

from app.extensions import db
from app.models import AuditLog, User, UserProfile
from app.services.privacy_service import create_deletion_request, process_request
from app.utils.pseudonymization import user_ref

from .conftest import PASSWORD, confirmation, post, seed, signin


def edit(client, app, uid, secret, **fields):
    return post(client, "/my-data/edit", {
        **confirmation(app, uid, secret), "username": "alice", "full_name": "Alice Silva",
        **fields,
    })


def test_registration_profile_and_required_email(app, client):
    fields = {"username": "nova", "password": PASSWORD, "password_confirmation": PASSWORD}
    response = post(client, "/register", fields)
    assert response.status_code == 200
    assert 'name="email"' in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(User)) is None
    assert post(client, "/register", {
        **fields, "email": "nova@example.com", "role": "admin", "full_name": "Ignorado",
    }).status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(User))
        assert user.profile.full_name is None
        assert user.email == "nova@example.com"
        assert user.role == "user" and not user.mfa_enabled
    assert post(client, "/register", {
        **fields, "email": "nova@example.com",
    }).status_code == 200


def test_old_account_edit_persist_and_audit(app, client):
    uid, secret = signin(client, app)
    with app.app_context():
        assert db.session.get(UserProfile, uid) is None
    assert client.get("/my-data/edit").status_code == 200
    response = edit(client, app, uid, secret, username="alice.nova")
    assert response.status_code == 302
    assert b"Alice Silva" in client.get("/my-data").data
    with app.app_context():
        profile = db.session.get(UserProfile, uid)
        assert profile.full_name == "Alice Silva" and profile.updated_at
        logs = db.session.scalars(db.select(AuditLog).where(
            AuditLog.user_ref == user_ref(uid),
            AuditLog.event_type == "dados_pessoais_alterados",
        )).all()
        assert len(logs) == 1 and logs[0].result == "sucesso"
        assert "Alice" not in str(logs[0].personal_data())
    assert post(client, "/logout").status_code == 302
    assert post(client, "/login", {"username": "alice.nova", "password": PASSWORD}).status_code == 302
    confirmation(app, uid, secret)
    assert post(client, "/mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    assert b"Alice Silva" in client.get("/my-data").data
    assert b"alice.nova" in client.get("/my-data").data


def test_profile_ownership_and_whitelist(app, client):
    uid, secret = signin(client, app)
    other, _ = seed(app, "outra")
    with app.app_context():
        db.session.get(User, other).profile = UserProfile(full_name="Nome privado")
        db.session.commit()
    assert b"Nome privado" not in client.get(f"/my-data?user_id={other}").data
    assert b"Nome privado" not in client.get(f"/my-data/edit?user_id={other}").data
    assert edit(client, app, uid, secret, user_id=other, role="admin", mfa_enabled="0", active="0").status_code == 302
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.role == "user" and user.active and user.mfa_enabled
        assert db.session.get(UserProfile, other).full_name == "Nome privado"
    assert client.get(f"/my-data/{other}").status_code == 404
    assert app.test_client().get("/my-data/edit").status_code == 302


@pytest.mark.parametrize("fields", [
    {"username": "outra"}, {"username": "x"}, {"username": "invalid space"},
    {"full_name": "x" * 121}, {"full_name": "Alice\nSilva"},
])
def test_profile_validation_preserves_input(app, client, fields):
    uid, secret = signin(client, app)
    seed(app, "outra")
    response = edit(client, app, uid, secret, **fields)
    assert response.status_code == 400
    assert b"Guardar" in response.data
    with app.app_context():
        assert db.session.get(User, uid).username == "alice"
        assert db.session.get(UserProfile, uid) is None
        assert db.session.scalar(db.select(AuditLog).where(
            AuditLog.event_type == "dados_pessoais_alterados",
        )).result == "falha"


def test_profile_requires_identity_and_csrf(app, client):
    uid, secret = signin(client, app)
    assert client.post("/my-data/edit", data={"username": "alice"}).status_code == 400
    assert edit(client, app, uid, secret, password="errada").status_code == 400
    assert edit(client, app, uid, secret, token="invalid").status_code == 400
    assert edit(client, app, uid, secret).status_code == 302
    # Recuperar exatamente o código utilizado na operação anterior.
    with app.app_context():
        step = db.session.get(User, uid).last_totp_step

    used_token = pyotp.TOTP(secret).at(step * 30)

    response = post(
        client,
        "/my-data/edit",
        {
            "username": "alice",
            "full_name": "Outro nome",
            "password": PASSWORD,
            "token": used_token,
        },
    )

    assert response.status_code == 400
    assert "Código MFA inválido ou já utilizado" in response.get_data(as_text=True)


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_profile_export_and_removal(app, client, fmt):
    uid, secret = signin(client, app)
    assert edit(client, app, uid, secret).status_code == 302
    response = post(client, "/export", {
        **confirmation(app, uid, secret), "categories": ["account"], "format": fmt,
    })
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Alice Silva" in body
    assert not any(value in body for value in ("password_hash", "totp_secret", secret))
    if fmt == "json":
        assert json.loads(body)["account"]["full_name"] == "Alice Silva"
    assert edit(client, app, uid, secret, full_name="").status_code == 302
    with app.app_context():
        assert db.session.get(UserProfile, uid).full_name is None


def test_profile_deletion_and_admin_minimization(app, client):
    uid, secret = signin(client, app)
    assert edit(client, app, uid, secret).status_code == 302
    admin = app.test_client()
    aid, _ = signin(admin, app, "administrador", "admin")
    # A gestão profissional necessita do nome; dados privados continuam excluídos.
    listing = admin.get("/admin/users").get_data(as_text=True)
    assert "Alice Silva" in listing
    assert "tax_number" not in listing and "password_hash" not in listing
    with app.app_context():
        assert create_deletion_request(uid)
        from app.models import DeletionRequest
        rid = db.session.scalar(db.select(DeletionRequest.id).where(DeletionRequest.user_id == uid))
        process_request(aid, rid, "process")
        process_request(aid, rid, "complete")
        assert db.session.get(User, uid) is None
        assert db.session.get(UserProfile, uid) is None


def test_username_revokes_other_sessions(app, client):
    uid, secret = signin(client, app)
    second = app.test_client()
    with client.session_transaction() as session:
        copied = dict(session)
    with second.session_transaction() as session:
        session.update(copied)
    assert second.get("/my-data").status_code == 200
    assert edit(client, app, uid, secret, username="novo.nome").status_code == 302
    assert client.get("/my-data").status_code == 200
    assert second.get("/my-data").status_code == 302


def test_profile_name_is_escaped(app, client):
    uid, secret = signin(client, app)
    name = '<script>alert("x")</script>'
    assert edit(client, app, uid, secret, full_name=name).status_code == 302
    response = client.get("/my-data")
    assert name not in response.get_data(as_text=True)
    assert b"&lt;script&gt;" in response.data
