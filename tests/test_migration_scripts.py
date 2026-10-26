import hashlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


def load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_database.py"
    spec = importlib.util.spec_from_file_location("migration_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_script_dry_run_and_copy_preserve_source(app, tmp_path, monkeypatch):
    module = load_script()
    module.ROOT = tmp_path
    source = tmp_path / "original.db"
    conn = sqlite3.connect(source)
    conn.execute("""CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,totp_secret TEXT,
        mfa_enabled INTEGER DEFAULT 0,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("INSERT INTO users(username,password_hash) VALUES('legacy','hash-preservado')")
    conn.commit()
    conn.close()
    for setting, key in [
        ("FLASK_SECRET_KEY", "SECRET_KEY"),
        ("AUDIT_HMAC_KEY", "AUDIT_HMAC_KEY"),
        ("MFA_ENC_KEY", "MFA_ENC_KEY"),
    ]:
        monkeypatch.setenv(setting, app.config[key])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(sys, "argv", ["migrate_database.py", "--source", str(source), "--dry-run"])
    module.main()
    target = tmp_path / "instance" / "secureaccess.db"
    assert not target.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    monkeypatch.setattr(sys, "argv", ["migrate_database.py", "--source", str(source)])
    module.main()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    conn = sqlite3.connect(target)
    assert conn.execute("SELECT username,password_hash,role FROM users").fetchone() == (
        "legacy",
        "hash-preservado",
        "user",
    )
    conn.close()
    assert (tmp_path / ".env").exists()
    with pytest.raises(SystemExit, match="destino já existe"):
        module.main()


def test_migration_script_refuses_missing_source(tmp_path, monkeypatch):
    module = load_script()
    module.ROOT = tmp_path
    monkeypatch.setattr(
        sys, "argv", ["migrate_database.py", "--source", str(tmp_path / "missing.db")]
    )
    with pytest.raises(SystemExit, match="não existe"):
        module.main()
    assert not (tmp_path / "instance" / "secureaccess.db").exists()
