import sqlite3

import pyotp
import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from .conftest import PASSWORD, post, seed, signin
from .db_helpers import get_db


def test_migration_preserves_original_schema_and_credentials(app, tmp_path):
    from flask_migrate import upgrade

    from app import create_app
    from app.extensions import db as orm_db

    path = tmp_path / "legacy.db"
    hashed = generate_password_hash(PASSWORD, method="pbkdf2:sha256")
    secret = pyotp.random_base32()
    ciphertext = app.extensions["fernet"].encrypt(secret.encode()).decode()
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,totp_secret TEXT,mfa_enabled INTEGER DEFAULT 0,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute(
        "INSERT INTO users(username,password_hash,totp_secret,mfa_enabled) VALUES(?,?,?,1)",
        ("legacy", hashed, ciphertext),
    )
    conn.commit()
    conn.close()
    migrated = create_app({**app.config, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + path.as_posix()})
    with migrated.app_context():
        upgrade()
        upgrade()
        orm_db.engine.dispose()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users").fetchone()
    assert (
        row["role"] == "user"
        and row["totp_secret"] == ciphertext
        and row["password_hash"] == hashed
    )
    assert check_password_hash(row["password_hash"], PASSWORD)
    assert app.extensions["fernet"].decrypt(row["totp_secret"].encode()) == secret.encode()
    assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0001_privacy"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE users SET role='auditor'")
    conn.close()
    legacy_client = migrated.test_client()
    assert post(
        legacy_client, "/login", {"username": "legacy", "password": PASSWORD}
    ).location.endswith("/mfa")
    assert post(legacy_client, "/mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    assert legacy_client.get("/dashboard").status_code == 200
    assert migrated.test_cli_runner().invoke(args=["db", "check"]).exit_code == 0


@pytest.mark.parametrize(
    "path",
    [
        "/admin/",
        "/admin/users",
        "/admin/logs",
        "/admin/deletions",
        "/admin/permissions",
        "/admin/settings",
        "/my-data",
        "/export",
        "/privacy",
    ],
)
def test_admin_pages_real_data(app, client, path):
    signin(client, app, "administrador", "admin")
    response = client.get(path)
    assert response.status_code == 200
    assert b"password_hash" not in response.data and b"Os meus dados</a>" not in response.data


def test_cli_dry_run_and_promotion(app):
    uid, _ = seed(app)
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "current"]).exit_code == 0
    assert runner.invoke(args=["promote-admin", "alice"]).exit_code == 0
    with app.app_context():
        assert (
            get_db().execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()[0] == "admin"
        )
    assert runner.invoke(args=["cleanup"]).exit_code == 0
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
