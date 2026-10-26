import sqlite3
import pytest
from werkzeug.security import generate_password_hash, check_password_hash
from .conftest import signin, seed, post, confirmation, PASSWORD
from secureaccess.db import get_db, migrate


def test_migration_preserves_original_schema_and_credentials(app):
    conn = sqlite3.connect(':memory:')
    conn.execute('''CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,totp_secret TEXT,mfa_enabled INTEGER DEFAULT 0,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    hashed = generate_password_hash(PASSWORD, method='pbkdf2:sha256')
    ciphertext = app.extensions['fernet'].encrypt(b'OLD-TOTP-SECRET').decode()
    conn.execute('INSERT INTO users(username,password_hash,totp_secret,mfa_enabled) VALUES(?,?,?,1)', ('legacy', hashed, ciphertext))
    conn.commit()
    migrate(conn)
    migrate(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM users').fetchone()
    assert row['role'] == 'user' and row['totp_secret'] == ciphertext and row['password_hash'] == hashed
    assert check_password_hash(row['password_hash'], PASSWORD)
    assert app.extensions['fernet'].decrypt(row['totp_secret'].encode()) == b'OLD-TOTP-SECRET'
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE users SET role='auditor'")


@pytest.mark.parametrize('path', ['/admin/', '/admin/users', '/admin/logs', '/admin/deletions', '/admin/permissions', '/admin/settings', '/my-data', '/export', '/privacy'])
def test_admin_pages_real_data(app, client, path):
    signin(client, app, 'administrador', 'admin')
    response = client.get(path)
    assert response.status_code == 200
    assert b'password_hash' not in response.data and b'Os meus dados</a>' not in response.data


def test_admin_actions_revoke_sessions(app, client):
    aid, secret = signin(client, app, 'administrador', 'admin')
    target_client = app.test_client()
    uid, _ = signin(target_client, app, 'bob')
    assert post(client, f'/admin/users/{aid}', {'action': 'user'}).status_code == 403
    assert post(client, f'/admin/users/{uid}', {**confirmation(app, aid, secret), 'action': 'deactivate'}).status_code == 302
    assert target_client.get('/dashboard').status_code == 302
    assert post(client, f'/admin/users/{uid}', {**confirmation(app, aid, secret), 'action': 'activate'}).status_code == 302
    assert target_client.get('/dashboard').status_code == 302
    assert post(client, f'/admin/users/{uid}', {**confirmation(app, aid, secret), 'action': 'admin'}).status_code == 302
    with app.app_context():
        assert get_db().execute('SELECT role FROM users WHERE id=?', (uid,)).fetchone()[0] == 'admin'
    assert post(client, '/admin/settings', confirmation(app, aid, secret)).status_code == 302


def test_cli_dry_run_and_promotion(app):
    uid, _ = seed(app)
    runner = app.test_cli_runner()
    assert runner.invoke(args=['migrate', '--dry-run']).exit_code == 0
    assert runner.invoke(args=['promote-admin', 'alice']).exit_code == 0
    with app.app_context():
        assert get_db().execute('SELECT role FROM users WHERE id=?', (uid,)).fetchone()[0] == 'admin'
    assert runner.invoke(args=['cleanup']).exit_code == 0
    assert runner.invoke(args=['migrate']).exit_code == 0
