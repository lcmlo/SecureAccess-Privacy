import functools
import hashlib
import hmac
import secrets
import time
from flask import abort, current_app, request, session
from flask_login import current_user, login_required, logout_user
from .db import get_db, now, cleanup

EVENTS = {
    'registo': 'Registo da conta', 'login': 'Login', 'mfa_falha': 'Falha na MFA',
    'mfa_ativada': 'MFA ativada', 'logout': 'Logout', 'exportacao': 'Exportação de dados',
    'pedido_eliminacao': 'Pedido de eliminação', 'eliminacao_processamento': 'Eliminação em processamento',
    'eliminacao_concluida': 'Eliminação concluída', 'conta_alterada': 'Estado da conta alterado',
    'perfil_alterado': 'Perfil alterado', 'perfil_alterado_cli': 'Perfil atribuído pela consola',
    'limpeza': 'Limpeza de registos',
}


def pseudonym(value):
    return hmac.new(current_app.config['AUDIT_HMAC_KEY'].encode(), value.encode(), hashlib.sha256).hexdigest()


def user_ref(uid):
    return pseudonym(f'user:{uid}')


def audit(event, ref=None, result='sucesso'):
    if event not in EVENTS or result not in ('sucesso', 'falha'):
        raise ValueError('Evento inválido')
    if ref is None:
        ref = user_ref(current_user.id)
    get_db().execute('INSERT INTO audit_logs(user_ref,event_type,event_timestamp,result) VALUES(?,?,?,?)',
                     (ref, event, now(), result))


def throttle(scope, identity):
    """Contadores atómicos; não confia em X-Forwarded-For enviado pelo cliente."""
    db = get_db()
    timestamp = int(time.time())
    for key in (f'{scope}:identity:{identity}', f'{scope}:origin:{request.remote_addr}'):
        bucket = pseudonym(key)
        db.execute('''INSERT INTO auth_attempts VALUES(?,1,?)
            ON CONFLICT(bucket) DO UPDATE SET
            attempts=CASE WHEN expires_at<=? THEN 1 ELSE attempts+1 END,
            expires_at=CASE WHEN expires_at<=? THEN excluded.expires_at ELSE expires_at END''',
            (bucket, timestamp + current_app.config['AUTH_WINDOW_SECONDS'], timestamp, timestamp))
        row = db.execute('SELECT attempts FROM auth_attempts WHERE bucket=?', (bucket,)).fetchone()
        db.commit()
        if row['attempts'] > current_app.config['AUTH_MAX_ATTEMPTS']:
            abort(429, description='Demasiadas tentativas. Aguarde 15 minutos.')


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != 'admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def confirm_identity():
    from werkzeug.security import check_password_hash
    from .auth import verify_totp
    throttle('confirm', str(current_user.id))
    row = get_db().execute('SELECT * FROM users WHERE id=?', (current_user.id,)).fetchone()
    if not check_password_hash(row['password_hash'], request.form.get('password', '')):
        abort(403, description='Não foi possível confirmar a identidade.')
    if not verify_totp(row, request.form.get('token', '')):
        abort(403, description='Código MFA inválido ou já utilizado. Aguarde pelo próximo código.')


def init_app(app):
    @app.context_processor
    def shared():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        return dict(csrf_token=session['csrf_token'], events=EVENTS,
                    retention=app.config['LOG_RETENTION_DAYS'], receipts_retention=app.config['RECEIPT_RETENTION_DAYS'])

    @app.before_request
    def protect():
        # Limpeza oportunista: não depende de tráfego para o agendamento documentado.
        if request.endpoint != 'static':
            cleanup()
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            supplied = request.form.get('csrf_token', '')
            expected = session.get('csrf_token', '')
            if not expected or not hmac.compare_digest(supplied, expected):
                abort(400, description='Formulário expirado. Recarregue a página.')
        if current_user.is_authenticated and time.time() - session.get('authenticated_at', 0) >= 1800:
            logout_user()
            session.clear()

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response
