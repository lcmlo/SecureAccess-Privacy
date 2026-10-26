"""Verifica a fábrica, Alembic, fronteiras de segurança e os 12 ecrãs."""

import re

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask import template_rendered
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AuditLog, DeletionRequest, User

from .conftest import post, seed, signin


def test_factory_blueprints_and_metadata(app):
    assert set(app.blueprints) == {"auth", "user", "privacy", "admin"}
    assert {
        User.__tablename__,
        AuditLog.__tablename__,
        DeletionRequest.__tablename__,
    } <= set(db.metadata.tables)
    with app.app_context(), db.engine.connect() as connection:
        migration = MigrationContext.configure(connection, opts={"compare_type": False})
        assert compare_metadata(migration, db.metadata) == []


@pytest.mark.parametrize(
    "path,template",
    [
        ("/dashboard", "user/dashboard.html"),
        ("/my-data", "user/my_data.html"),
        ("/history", "user/history.html"),
        ("/privacy", "user/privacy_center.html"),
        ("/export", "user/export_data.html"),
        ("/deletion", "user/deletion_request.html"),
        ("/admin/", "admin/dashboard.html"),
        ("/admin/users", "admin/users.html"),
        ("/admin/logs", "admin/audit_logs.html"),
        ("/admin/deletions", "admin/deletion_requests.html"),
        ("/admin/permissions", "admin/permissions.html"),
        ("/admin/settings", "admin/settings.html"),
    ],
)
def test_twelve_screens_layouts_and_components(app, client, path, template):
    administrative = path.startswith("/admin")
    signin(client, app, role="admin" if administrative else "user")
    rendered = []

    def capture(sender, template, context, **extra):
        rendered.append(template.name)

    template_rendered.connect(capture, app)
    try:
        response = client.get(path)
    finally:
        template_rendered.disconnect(capture, app)
    assert response.status_code == 200 and template in rendered
    body = response.get_data(as_text=True)
    nav = re.search(r"<nav.*?</nav>", body, re.S).group()
    assert len(re.findall(r"<a\b", nav)) == 6
    assert ("Menu administrativo" in nav) == administrative
    if not administrative:
        assert "/admin/" not in body


def test_csrf_signed_tampered_and_missing(app, client):
    response = client.get("/register")
    assert response.status_code == 200
    with client.session_transaction() as session:
        unsigned = session["csrf_token"]
    assert client.post("/register", data={"csrf_token": unsigned}).status_code == 400
    assert client.post("/register", data={"csrf_token": "alterado"}).status_code == 400
    assert client.post("/register").status_code == 400


def test_pending_session_revoked_by_version_change(app, client):
    import pyotp

    from .conftest import PASSWORD

    uid, secret = seed(app)
    assert post(client, "/login", {"username": "alice", "password": PASSWORD}).status_code == 302
    with app.app_context():
        db.session.get(User, uid).session_version += 1
        db.session.commit()
    response = post(client, "/mfa", {"token": pyotp.TOTP(secret).now()})
    assert response.status_code == 302 and response.location.endswith("/login")


def test_database_role_constraint(app):
    with app.app_context():
        db.session.add(User(username="inválido", password_hash="hash", role="auditor"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_static_assets_and_error_pages(app, client):
    for asset in [
        "css/main.css",
        "css/auth.css",
        "css/user.css",
        "css/admin.css",
        "js/main.js",
        "js/user.js",
        "js/admin.js",
        "images/logo.svg",
    ]:
        assert client.get("/static/" + asset).status_code == 200
    assert "Página não encontrada" in client.get("/inexistente").get_data(as_text=True)
    assert client.get("/logout").status_code == 405
