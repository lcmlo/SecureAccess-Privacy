"""Os scripts de manutenção são executados apenas sobre SQLite temporário."""

import os
import subprocess
import sys
from pathlib import Path

from app.extensions import db
from app.models import AuditLog, User
from app.services.audit_service import now

from .conftest import seed


def isolated_environment(app):
    env = os.environ.copy()
    with app.app_context():
        env["MFA_DB_PATH"] = db.engine.url.database
    env.update(
        FLASK_SECRET_KEY=app.config["SECRET_KEY"],
        AUDIT_HMAC_KEY=app.config["AUDIT_HMAC_KEY"],
        MFA_ENC_KEY=app.config["MFA_ENC_KEY"],
        APP_ENV="testing",
        COOKIE_SECURE="0",
    )
    return env


def test_cleanup_script_only_removes_expired_test_rows(app, tmp_path):
    with app.app_context():
        db.session.add_all(
            [
                AuditLog(
                    user_ref="old",
                    event_type="login",
                    result="sucesso",
                    event_timestamp="2000-01-01 00:00:00",
                ),
                AuditLog(
                    user_ref="new", event_type="login", result="sucesso", event_timestamp=now()
                ),
            ]
        )
        db.session.commit()
    script = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_logs.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=isolated_environment(app),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "1 registos" in result.stdout
    with app.app_context():
        assert db.session.scalars(db.select(AuditLog.user_ref)).all() == ["new"]


def test_create_admin_script_promotes_only_ready_test_account(app, tmp_path):
    uid, _ = seed(app)
    script = Path(__file__).resolve().parents[1] / "scripts" / "create_admin.py"
    subprocess.run(
        [sys.executable, str(script), "alice"],
        cwd=tmp_path,
        env=isolated_environment(app),
        capture_output=True,
        text=True,
        check=True,
    )
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.role == "admin" and user.session_version == 1
