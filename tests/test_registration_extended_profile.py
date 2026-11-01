import base64
import datetime
import io
import time

import pyotp
import pytest
from flask_migrate import upgrade
from PIL import Image
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import User, UserProfile
from app.services import profile_service
from app.services.auth_service import register
from app.services.privacy_service import create_deletion_request, process_request
from app.utils.identifiers import EMAIL_TAKEN, USERNAME_TAKEN

from .conftest import PASSWORD, confirmation, post, seed, signin


@pytest.fixture(autouse=True)
def stable_totp_clock(monkeypatch):
    timestamp = time.time()
    original_datetime = datetime.datetime

    class FrozenDatetime(original_datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(timestamp, tz)

    monkeypatch.setattr(time, "time", lambda: timestamp)
    monkeypatch.setattr(datetime, "datetime", FrozenDatetime)


def registration(client, **fields):
    return post(client, "/register", {"username": "nova", "email": "nova@example.com", "password": PASSWORD, "password_confirmation": fields.get("password", PASSWORD), **fields})


def update(client, app, uid, secret, **fields):
    return post(client, "/my-data/edit", {
        **confirmation(app, uid, secret), "username": "alice", "full_name": "Alice Silva",
        "email": "alice@example.com", **fields,
    })


def photo(color="red"):
    output = io.BytesIO()
    image = Image.new("RGB", (800, 600), color)
    exif = Image.Exif()
    exif[270] = "private metadata"
    image.save(output, format="JPEG", exif=exif)
    output.seek(0)
    return output


def test_registration_fields_and_mfa(app, client):
    html = client.get("/register").get_data(as_text=True)
    assert 'name="email"' in html and 'name="password_confirmation"' in html
    assert 'name="full_name"' not in html
    assert registration(client, username="  Nova  ", email="  Name+tag@EXAMPLE.COM  ", role="admin").status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(User))
        assert (user.username, user.email, user.role) == ("Nova", "name+tag@example.com", "user")
        assert user.password_hash != PASSWORD and user.profile is not None
    response = post(client, "/login", {"username": "NOVA", "password": PASSWORD})
    assert response.location.endswith("/setup-mfa")
    assert client.get("/my-data").status_code == 302
    client.get("/setup-mfa")
    with app.app_context():
        user = db.session.scalar(db.select(User))
        secret = app.extensions["fernet"].decrypt(user.totp_secret.encode()).decode()
    assert post(client, "/setup-mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    assert client.get("/my-data").status_code == 200


@pytest.mark.parametrize("confirmation", [None, "", "Outra-palavra-passe!"])
def test_registration_requires_matching_password_confirmation(app, client, confirmation):
    fields = {"username": "nova", "email": "nova@example.com", "password": PASSWORD}
    if confirmation is not None:
        fields["password_confirmation"] = confirmation
    response = post(client, "/register", fields)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "A confirmação da palavra-passe não coincide." in html
    assert 'value="nova"' in html and 'value="nova@example.com"' in html
    assert PASSWORD not in html
    with app.app_context():
        assert db.session.scalar(db.select(User)) is None


@pytest.mark.parametrize("fields,message", [
    ({"username": "nova", "email": "other@example.com"}, USERNAME_TAKEN),
    ({"username": "NoVa", "email": "other@example.com"}, USERNAME_TAKEN),
    ({"username": "  NOVA  ", "email": "other@example.com"}, USERNAME_TAKEN),
    ({"username": "other"}, EMAIL_TAKEN),
    ({"username": "other", "email": "  NOVA@EXAMPLE.COM  "}, EMAIL_TAKEN),
])
def test_registration_duplicates(app, client, fields, message):
    assert registration(client).status_code == 302
    response = registration(client, **fields)
    assert response.status_code == 200 and message in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 1


@pytest.mark.parametrize("email", ["", "invalid", "a@", "@example.com", "a..b@example.com", "a@-example.com", "a@example", "a\n@example.com"])
def test_registration_invalid_email(app, client, email):
    assert registration(client, email=email).status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(User)) is None


def test_email_provider_rules_are_not_applied(app, client):
    assert registration(client, email="a.b+tag@example.com").status_code == 302
    assert registration(client, username="second", email="ab@example.com").status_code == 302
    assert registration(client, username="third", email="a.b@example.com").status_code == 302


@pytest.mark.parametrize("column,value,message", [
    ("username", " NOVA ", USERNAME_TAKEN),
    ("email", " NOVA@EXAMPLE.COM ", EMAIL_TAKEN),
])
def test_database_and_integrity_error_fallback(app, client, monkeypatch, column, value, message):
    assert registration(client).status_code == 302
    with app.app_context():
        with pytest.raises(IntegrityError):
            db.session.execute(db.text("INSERT INTO users(username,email,password_hash) VALUES (:username,:email,'hash')"), {
                "username": value if column == "username" else "other",
                "email": value if column == "email" else "other@example.com",
            })
            db.session.commit()
        db.session.rollback()
        # Simula outra transação a gravar depois da verificação preliminar.
        monkeypatch.setattr("app.services.auth_service.check_available", lambda *args: None)
        from werkzeug.exceptions import BadRequest
        with pytest.raises(BadRequest, match=message):
            register(value if column == "username" else "other", PASSWORD, "local", email=value if column == "email" else "other@example.com")


def test_unicode_username_database_uniqueness(app):
    with app.app_context():
        db.session.add(User(username="Álvaro", password_hash="hash"))
        db.session.commit()
        db.session.add(User(username="ÁLVARO", password_hash="hash"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_extended_profile_photo_persistence_and_export(app, client):
    uid, secret = signin(client, app)
    fields = {"birth_date": "2000-06-15", "gender": "outro", "tax_number": "123456789", "address": "Morada fictícia", "marital_status": "solteiro"}
    assert update(client, app, uid, secret, photo=(photo(), "image.jpg"), job_title="CEO", role="admin", **fields).status_code == 302
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.profile.birth_date.isoformat() == fields["birth_date"] and user.profile.address == fields["address"]
        assert user.profile.job_title is None and user.role == "user"
        saved = user.profile.photo
        with Image.open(io.BytesIO(saved)) as image:
            assert image.size == (512, 384) and not image.getexif()
    response = client.get("/my-data/photo")
    assert response.status_code == 200 and response.mimetype == "image/jpeg"
    assert response.data == saved and response.headers["Cache-Control"] == "no-store"
    assert b"alice@example.com" in client.get("/my-data").data
    html = client.get("/my-data/edit").get_data(as_text=True)
    assert 'value="2000-06-15"' in html and 'value="Morada fictícia"' in html
    post(client, "/logout")
    assert post(client, "/login", {"username": "alice", "password": PASSWORD}).status_code == 302
    confirmation(app, uid, secret)
    assert post(client, "/mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    assert client.get("/my-data/photo").data == saved
    response = post(client, "/export", {**confirmation(app, uid, secret), "categories": ["account"], "format": "json"})
    data = response.get_json()["account"]
    assert data["birth_date"] == "2000-06-15" and data["email"] == "alice@example.com"
    assert base64.b64decode(data["photo_jpeg_base64"]) == saved
    assert update(client, app, uid, secret, photo=(photo("blue"), "second.jpg"), **fields).status_code == 302
    assert client.get("/my-data/photo").data != saved
    assert update(client, app, uid, secret, remove_photo="1", **fields).status_code == 302
    assert client.get("/my-data/photo").status_code == 404


def test_change_identifiers_and_reject_conflicts(app, client, monkeypatch):
    uid, secret = signin(client, app)
    assert update(client, app, uid, secret, username="alice.new", email="NEW@example.com").status_code == 302
    other, _ = seed(app, "other")
    with app.app_context():
        db.session.get(User, other).email = "other@example.com"
        db.session.commit()
    for username, email, message in [("OTHER", "new@example.com", USERNAME_TAKEN), ("alice.new", "OTHER@EXAMPLE.COM", EMAIL_TAKEN)]:
        response = update(client, app, uid, secret, username=username, email=email)
        assert response.status_code == 400 and message in response.get_data(as_text=True)
    monkeypatch.setattr(profile_service, "check_available", lambda *args: None)
    assert update(client, app, uid, secret, email="other@example.com").status_code == 400
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.username == "alice.new" and user.email == "new@example.com"


@pytest.mark.parametrize("fields", [
    {"birth_date": "9999-01-01"}, {"birth_date": "2025-02-29"}, {"birth_date": "2026-13-01"}, {"gender": "invalid"},
    {"tax_number": "123"}, {"tax_number": "123456788"}, {"address": "x" * 301},
    {"marital_status": "invalid"}, {"email": "bad-email"},
])
def test_invalid_profile_fields(app, client, fields):
    uid, secret = signin(client, app)
    assert update(client, app, uid, secret, **fields).status_code == 400
    with app.app_context():
        assert db.session.get(UserProfile, uid) is None


@pytest.mark.parametrize("content", [b'<svg onload="alert(1)"></svg>', b"not an image", b"x" * (2 * 1024 * 1024 + 1)], ids=["svg", "invalid", "too-large"])
def test_invalid_uploads_are_rejected(app, client, content):
    uid, secret = signin(client, app)
    assert update(client, app, uid, secret, photo=(io.BytesIO(content), "photo.jpg")).status_code == 400
    with app.app_context():
        assert db.session.get(UserProfile, uid) is None


def test_photo_ownership_and_csrf(app, client):
    uid, secret = signin(client, app)
    assert update(client, app, uid, secret, photo=(photo(), "photo.jpg")).status_code == 302
    other = app.test_client()
    oid, other_secret = signin(other, app, "other")
    assert other.get(f"/my-data/photo?user_id={uid}").status_code == 404
    assert app.test_client().get("/my-data/photo").status_code == 302
    assert client.get(f"/my-data/photo/{uid}").status_code == 404
    assert other.post("/my-data/edit", data={"photo": (photo(), "photo.jpg")}).status_code == 400
    assert update(other, app, oid, other_secret, username="other", email="other@example.com", user_id=uid).status_code == 302
    assert client.get("/my-data/photo").status_code == 200


@pytest.mark.parametrize("field", ["username", "email"])
def test_migration_refuses_conflicts_without_changes(app, tmp_path, field, caplog):
    path = tmp_path / "conflicts.db"
    migrated = create_app({**app.config, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + path.as_posix()})
    with migrated.app_context():
        upgrade(revision="0002_user_profiles")
        with db.engine.begin() as connection:
            if field == "username":
                connection.execute(db.text("INSERT INTO users(username,password_hash) VALUES ('Miguel','hash1'), ('miguel','hash2')"))
            else:
                connection.execute(db.text("ALTER TABLE users ADD COLUMN email VARCHAR(254)"))
                connection.execute(db.text("INSERT INTO users(username,email,password_hash) VALUES ('first','Email@example.com','hash1'), ('second','email@EXAMPLE.COM','hash2')"))
        with pytest.raises(SystemExit):
            upgrade()
        assert f"conflitos de {field}" in caplog.text
        with db.engine.connect() as connection:
            assert connection.execute(db.text("SELECT version_num FROM alembic_version")).scalar() == "0002_user_profiles"
            assert connection.execute(db.text("SELECT count(*) FROM users")).scalar() == 2
            if field == "username":
                assert "email" not in {row[1] for row in connection.execute(db.text("PRAGMA table_info(users)"))}
        db.engine.dispose()


def test_photo_persists_across_app_restart_and_is_deleted(app, client):
    uid, secret = signin(client, app)
    assert update(client, app, uid, secret, photo=(photo(), "photo.jpg"), birth_date="1996-06-15").status_code == 302
    restarted = create_app(dict(app.config))
    fresh_client = restarted.test_client()
    confirmation(app, uid, secret)
    assert post(fresh_client, "/login", {"username": "ALICE", "password": PASSWORD}).location.endswith("/mfa")
    assert post(fresh_client, "/mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    assert fresh_client.get("/my-data/photo").status_code == 200
    assert 'value="1996-06-15"' in fresh_client.get("/my-data/edit").get_data(as_text=True)
    aid, _ = seed(app, "admin", "admin")
    with app.app_context():
        from app.models import DeletionRequest
        assert create_deletion_request(uid)
        rid = db.session.scalar(db.select(DeletionRequest.id).where(DeletionRequest.user_id == uid))
        process_request(aid, rid, "process")
        process_request(aid, rid, "complete")
        assert db.session.get(UserProfile, uid) is None
    assert fresh_client.get("/my-data/photo").status_code == 302
    with restarted.app_context():
        db.session.remove()
        db.engine.dispose()
