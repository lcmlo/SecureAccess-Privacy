"""Migração aditiva e transacional; preserva hashes e segredos existentes."""
import sqlite3
from datetime import datetime, timezone, timedelta
import click
from flask import current_app, g


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
        g.db.execute('PRAGMA secure_delete=ON')
    return g.db


def migrate(conn):
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, totp_secret TEXT, mfa_enabled INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cols = {r[1] for r in conn.execute('PRAGMA table_info(users)')}
        for name, definition in {
            'role': "TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin'))",
            'active': 'INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))',
            'session_version': 'INTEGER NOT NULL DEFAULT 0', 'last_totp_step': 'INTEGER',
        }.items():
            if name not in cols:
                conn.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
        conn.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_ref TEXT NOT NULL,
            event_type TEXT NOT NULL, event_timestamp TEXT NOT NULL,
            result TEXT NOT NULL CHECK(result IN ('sucesso','falha')))''')
        conn.execute('CREATE INDEX IF NOT EXISTS audit_ref_time ON audit_logs(user_ref,event_timestamp)')
        conn.execute('CREATE INDEX IF NOT EXISTS audit_time ON audit_logs(event_timestamp)')
        conn.execute('''CREATE TABLE IF NOT EXISTS deletion_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            requested_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','em processamento','concluído')),
            completed_at TEXT,
            CHECK ((status='concluído' AND completed_at IS NOT NULL) OR
                   (status!='concluído' AND completed_at IS NULL)))''')
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_open_request ON deletion_requests(user_id) WHERE status!='concluído'")
        conn.execute('''CREATE TABLE IF NOT EXISTS deletion_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL REFERENCES deletion_requests(id) ON DELETE CASCADE,
            status TEXT NOT NULL, changed_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS auth_attempts (
            bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at INTEGER NOT NULL)''')
        conn.execute('PRAGMA user_version=1')
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def cleanup():
    db = get_db()
    def cutoff(days):
        return (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    logs = db.execute('DELETE FROM audit_logs WHERE event_timestamp < ?', (cutoff(current_app.config['LOG_RETENTION_DAYS']),)).rowcount
    receipts = db.execute("DELETE FROM deletion_requests WHERE status='concluído' AND completed_at < ?", (cutoff(current_app.config['RECEIPT_RETENTION_DAYS']),)).rowcount
    db.execute("DELETE FROM auth_attempts WHERE expires_at < CAST(strftime('%s','now') AS INTEGER)")
    db.commit()
    return logs, receipts


def init_app(app):
    @app.teardown_appcontext
    def close_db(error=None):
        conn = g.pop('db', None)
        if conn is not None:
            conn.close()

    @app.cli.command('migrate')
    @click.option('--dry-run', is_flag=True)
    def migrate_command(dry_run):
        source = get_db()
        if dry_run:
            target = sqlite3.connect(':memory:')
            source.backup(target)
            migrate(target)
            target.close()
        else:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
            target = sqlite3.connect(str(app.config['DATABASE']) + f'.{stamp}.pre-migration.bak')
            source.backup(target)
            target.close()
            migrate(source)
        click.echo('Migração validada.' if dry_run else 'Migração concluída; cópia de segurança criada.')

    @app.cli.command('cleanup')
    def cleanup_command():
        logs, receipts = cleanup()
        click.echo(f'Eliminados: {logs} registos e {receipts} comprovativos expirados.')

    @app.cli.command('promote-admin')
    @click.argument('username')
    def promote_admin(username):
        from .security import audit, user_ref
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not row or not row['active'] or not row['mfa_enabled']:
            raise click.ClickException('É necessária uma conta ativa com MFA configurada.')
        db.execute("UPDATE users SET role='admin', session_version=session_version+1 WHERE id=?", (row['id'],))
        audit('perfil_alterado_cli', user_ref(row['id']))
        db.commit()
        click.echo('Perfil administrativo atribuído; sessões anteriores revogadas.')
