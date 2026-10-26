import base64
import io
import re
import secrets
import sqlite3
import time
import pyotp
import qrcode
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, session, abort
from flask_login import UserMixin, current_user, login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from . import login_manager
from .db import get_db
from .security import audit, user_ref, pseudonym, throttle

bp = Blueprint('auth', __name__)
DUMMY_HASH = generate_password_hash('unavailable-account-password')


class User(UserMixin):
    def __init__(self, row):
        self.id, self.username, self.role = row['id'], row['username'], row['role']
        self.mfa_enabled, self.created_at = row['mfa_enabled'], row['created_at']


@login_manager.user_loader
def load_user(uid):
    row = get_db().execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone()
    if row and session.get('version') == row['session_version']:
        return User(row)
    return None


def decrypt(ciphertext):
    return current_app.extensions['fernet'].decrypt(ciphertext.encode()).decode()


def verify_totp(row, token):
    if not re.fullmatch(r'[0-9]{6}', token) or not row['totp_secret']:
        return False
    totp = pyotp.TOTP(decrypt(row['totp_secret']))
    step = int(time.time()) // 30
    if not totp.verify(token, valid_window=0):
        return False
    changed = get_db().execute('''UPDATE users SET last_totp_step=? WHERE id=?
        AND (last_totp_step IS NULL OR last_totp_step<?)''', (step, row['id'], step)).rowcount
    get_db().commit()
    return changed == 1


def finish_login(uid):
    row = get_db().execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone()
    if not row:
        abort(403)
    session.clear()
    session.permanent = True
    session['version'] = row['session_version']
    session['authenticated_at'] = time.time()
    session['csrf_token'] = secrets.token_urlsafe(32)
    login_user(User(row))
    audit('login')
    get_db().commit()
    return redirect(url_for('privacy.dashboard'))


def pending_user():
    uid = session.get('pending_user_id')
    if not uid or time.time() - session.get('pending_at', 0) > 300:
        session.clear()
        return None
    row = get_db().execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone()
    if row and row['session_version'] == session.get('pending_version'):
        return row
    session.clear()
    return None


@bp.route('/')
def index():
    return redirect(url_for('privacy.dashboard' if current_user.is_authenticated else 'auth.login'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        throttle('register', request.remote_addr or 'local')
        username, password = request.form.get('username', '').strip(), request.form.get('password', '')
        if not re.fullmatch(r'[\w.-]{3,64}', username) or not 12 <= len(password) <= 128:
            flash('Use um nome de utilizador de 3 a 64 caracteres e uma palavra-passe de 12 a 128 caracteres.')
        else:
            db = get_db()
            try:
                cursor = db.execute('INSERT INTO users(username,password_hash) VALUES(?,?)', (username, generate_password_hash(password)))
                audit('registo', user_ref(cursor.lastrowid))
                db.commit()
                flash('Registo efetuado. Autentique-se e configure a MFA.')
                return redirect(url_for('auth.login'))
            except sqlite3.IntegrityError:
                db.rollback()
                flash('Não foi possível criar a conta com os dados indicados.')
    return render_template('register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        throttle('login', username.casefold())
        row = get_db().execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        valid = check_password_hash(row['password_hash'] if row else DUMMY_HASH, request.form.get('password', ''))
        if row and row['active'] and valid:
            session.clear()
            session['pending_user_id'] = row['id']
            session['pending_at'] = time.time()
            session['pending_version'] = row['session_version']
            return redirect(url_for('auth.mfa' if row['mfa_enabled'] else 'auth.setup_mfa'))
        audit('login', user_ref(row['id']) if row else pseudonym('unknown:' + username), 'falha')
        get_db().commit()
        flash('Credenciais inválidas ou conta indisponível.')
    return render_template('login.html')


@bp.route('/setup-mfa', methods=['GET', 'POST'])
def setup_mfa():
    row = pending_user()
    if not row:
        return redirect(url_for('auth.login'))
    if row['mfa_enabled']:
        return redirect(url_for('auth.mfa'))
    if not row['totp_secret']:
        encrypted = current_app.extensions['fernet'].encrypt(pyotp.random_base32().encode()).decode()
        get_db().execute('UPDATE users SET totp_secret=? WHERE id=?', (encrypted, row['id']))
        get_db().commit()
        row = pending_user()
    if request.method == 'POST':
        throttle('mfa', str(row['id']))
        if verify_totp(row, request.form.get('token', '')):
            get_db().execute('UPDATE users SET mfa_enabled=1 WHERE id=?', (row['id'],))
            audit('mfa_ativada', user_ref(row['id']))
            get_db().commit()
            return finish_login(row['id'])
        audit('mfa_falha', user_ref(row['id']), 'falha')
        get_db().commit()
        flash('Código inválido ou já utilizado.')
    secret = decrypt(row['totp_secret'])
    uri = pyotp.TOTP(secret).provisioning_uri(name=row['username'], issuer_name='SecureAccess Privacy')
    buffer = io.BytesIO()
    qrcode.make(uri).save(buffer, format='PNG')
    return render_template('setup_mfa.html', secret=secret, qr_b64=base64.b64encode(buffer.getvalue()).decode())


@bp.route('/mfa', methods=['GET', 'POST'])
def mfa():
    row = pending_user()
    if not row:
        return redirect(url_for('auth.login'))
    if not row['mfa_enabled']:
        return redirect(url_for('auth.setup_mfa'))
    if request.method == 'POST':
        throttle('mfa', str(row['id']))
        if verify_totp(row, request.form.get('token', '')):
            return finish_login(row['id'])
        audit('mfa_falha', user_ref(row['id']), 'falha')
        get_db().commit()
        flash('Código inválido ou já utilizado.')
    return render_template('mfa.html')


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    audit('logout')
    get_db().commit()
    logout_user()
    session.clear()
    return redirect(url_for('auth.login'))
