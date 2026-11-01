from datetime import date, timedelta

import pyotp
import pytest
from flask_migrate import upgrade
from werkzeug.exceptions import BadRequest

from app import create_app
from app.extensions import db
from app.models import AuditLog, DeletionRequest, User, UserProfile
from app.services.privacy_service import create_deletion_request, process_request
from app.utils.birth_dates import calculate_age, parse_birth_date

from .conftest import PASSWORD, confirmation, post, seed, signin
from .test_registration_extended_profile import stable_totp_clock as stable_totp_clock

pytestmark = pytest.mark.usefixtures("stable_totp_clock")


@pytest.fixture
def today(monkeypatch):
    value = date(2026, 6, 15)
    monkeypatch.setattr("app.utils.birth_dates.current_date", lambda: value)
    monkeypatch.setattr("app.routes.user.current_date", lambda: value)
    return value


def save(client, app, uid, secret, birth_date="2003-06-15", **extra):
    return post(client, "/my-data/edit", {
        **confirmation(app, uid, secret), "username": "alice", "full_name": "Alice",
        "birth_date": birth_date, **extra,
    })


@pytest.mark.parametrize("born,today,expected", [
    (date(2003, 6, 15), date(2026, 1, 1), 22),
    (date(2003, 6, 15), date(2026, 6, 14), 22),
    (date(2003, 6, 15), date(2026, 6, 15), 23),
    (date(2003, 6, 15), date(2026, 6, 16), 23),
    (date(2003, 6, 15), date(2031, 6, 15), 28),
    (date(2000, 2, 29), date(2025, 2, 28), 24),
    (date(2000, 2, 29), date(2025, 3, 1), 25),
    (date(2000, 2, 29), date(2024, 2, 28), 23),
    (date(2000, 2, 29), date(2024, 2, 29), 24),
    (date(2026, 6, 15), date(2026, 6, 15), 0),
    (date(1, 1, 1), date(2026, 6, 15), 2025),
    (None, date(2026, 6, 15), None),
])
def test_age_uses_month_day_and_leap_year_rule(born, today, expected):
    assert calculate_age(born, today) == expected


@pytest.mark.parametrize("value", ["2026-06-16", "2025-02-29", "1900-02-29", "2000-02-30", "2003-13-01", "2003-00-01", "2003-06-31", "0000-01-01", "20030615", "03-06-15", "15/06/2003", "not-a-date"])
def test_invalid_or_future_birth_date_does_not_change_profile(app, client, today, value):
    uid, secret = signin(client, app)
    assert save(client, app, uid, secret).status_code == 302
    response = save(client, app, uid, secret, birth_date=value)
    assert response.status_code == 400
    assert "Data de nascimento" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(UserProfile, uid).birth_date == date(2003, 6, 15)


def test_birth_date_save_view_login_export_and_clear(app, client, today):
    uid, secret = signin(client, app)
    assert save(client, app, uid, secret, age="99", legacy_age="99").status_code == 302
    with app.app_context():
        profile = db.session.get(UserProfile, uid)
        assert profile.birth_date == date(2003, 6, 15) and profile.age == 23
        assert profile.legacy_age is None
        assert "age" not in {column["name"] for column in db.inspect(db.engine).get_columns("user_profiles")}
        log = db.session.scalar(db.select(AuditLog).where(AuditLog.event_type == "dados_pessoais_alterados"))
        assert "2003" not in str(log.personal_data())
    body = client.get("/my-data").get_data(as_text=True)
    assert "15/06/2003" in body and "23 anos" in body
    form = client.get("/my-data/edit").get_data(as_text=True)
    assert 'type="date"' in form and 'value="2003-06-15"' in form and 'max="2026-06-15"' in form
    assert 'name="age"' not in form
    assert post(client, "/logout").status_code == 302
    assert post(client, "/login", {"username": "alice", "password": PASSWORD}).location.endswith("/mfa")
    confirmation(app, uid, secret)
    assert post(client, "/mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    assert 'value="2003-06-15"' in client.get("/my-data/edit").get_data(as_text=True)
    for fmt in ("json", "csv"):
        response = post(client, "/export", {**confirmation(app, uid, secret), "categories": ["account"], "format": fmt})
        assert response.status_code == 200 and "2003-06-15" in response.get_data(as_text=True)
        if fmt == "json":
            assert response.get_json()["account"]["age"] == 23
    assert save(client, app, uid, secret, birth_date="").status_code == 302
    with app.app_context():
        assert db.session.get(UserProfile, uid).birth_date is None
        assert db.session.get(UserProfile, uid).age is None
    assert "Não indicada" in client.get("/my-data").get_data(as_text=True)


def test_age_recomputed_without_edit(app, client, monkeypatch, today):
    uid, secret = signin(client, app)
    assert save(client, app, uid, secret).status_code == 302
    monkeypatch.setattr("app.utils.birth_dates.current_date", lambda: date(2031, 6, 14))
    assert "27 anos" in client.get("/my-data").get_data(as_text=True)
    monkeypatch.setattr("app.utils.birth_dates.current_date", lambda: date(2031, 6, 15))
    assert "28 anos" in client.get("/my-data").get_data(as_text=True)


def test_old_dates_are_valid_without_arbitrary_age_limit(today):
    assert parse_birth_date("0001-01-01", today) == date(1, 1, 1)
    assert parse_birth_date("1900-01-01", today) == date(1900, 1, 1)
    assert parse_birth_date("2000-02-29", today) == date(2000, 2, 29)
    assert parse_birth_date("", today) is None
    assert parse_birth_date(today.isoformat(), today) == today
    with pytest.raises(BadRequest, match="futura"):
        parse_birth_date((today + timedelta(days=1)).isoformat(), today)


def test_ownership_and_deletion_include_birth_date(app, client, today):
    uid, secret = signin(client, app)
    other, _ = seed(app, "other")
    with app.app_context():
        db.session.get(User, other).profile = UserProfile(birth_date=date(1990, 1, 1))
        db.session.commit()
    assert save(client, app, uid, secret, user_id=other).status_code == 302
    assert "1990" not in client.get(f"/my-data?user_id={other}").get_data(as_text=True)
    assert app.test_client().get("/my-data").status_code == 302
    aid, _ = seed(app, "admin", "admin")
    with app.app_context():
        assert db.session.get(UserProfile, other).birth_date == date(1990, 1, 1)
        assert create_deletion_request(uid)
        rid = db.session.scalar(db.select(DeletionRequest.id).where(DeletionRequest.user_id == uid))
        process_request(aid, rid, "process")
        process_request(aid, rid, "complete")
        assert db.session.get(UserProfile, uid) is None
        assert db.session.get(UserProfile, other).birth_date == date(1990, 1, 1)


def test_migration_preserves_legacy_ages_without_inventing_dates(app, tmp_path):
    path = tmp_path / "old_ages.db"
    migrated = create_app({**app.config, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + path.as_posix()})
    with migrated.app_context():
        upgrade(revision="0003_registration_profile")
        with db.engine.begin() as connection:
            connection.execute(db.text("INSERT INTO users(id,username,password_hash) VALUES (1,'legacy','same-hash'),(2,'empty','same-hash')"))
            connection.execute(db.text("INSERT INTO user_profiles(user_id,age) VALUES(1,42),(2,NULL)"))
        upgrade()
        upgrade()
        with db.engine.connect() as connection:
            assert connection.execute(db.text("SELECT user_id,legacy_age,birth_date FROM user_profiles ORDER BY user_id")).all() == [(1, 42, None), (2, None, None)]
            assert connection.execute(db.text("SELECT username,password_hash FROM users WHERE id=1")).one() == ("legacy", "same-hash")
        assert db.session.get(UserProfile, 1).age is None
        assert db.session.get(User, 1).public_data()["legacy_age"] == 42
        assert migrated.test_cli_runner().invoke(args=["db", "check"]).exit_code == 0
        db.session.remove()
        db.engine.dispose()
