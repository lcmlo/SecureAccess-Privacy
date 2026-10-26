import os
from datetime import timedelta
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import LoginManager
from werkzeug.exceptions import default_exceptions

login_manager = LoginManager()


def create_app(config=None):
    load_dotenv()
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    app.config.from_mapping(
        SECRET_KEY=os.getenv('FLASK_SECRET_KEY'), MFA_ENC_KEY=os.getenv('MFA_ENC_KEY'),
        AUDIT_HMAC_KEY=os.getenv('AUDIT_HMAC_KEY'),
        DATABASE=os.getenv('MFA_DB_PATH', str(root / 'mfa.db')),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30), SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=32768, MAX_FORM_MEMORY_SIZE=32768, MAX_FORM_PARTS=50,
        LOG_RETENTION_DAYS=90, RECEIPT_RETENTION_DAYS=90,
        AUTH_WINDOW_SECONDS=900, AUTH_MAX_ATTEMPTS=5,
    )
    if config:
        app.config.update(config)
    if not app.config['SECRET_KEY'] or len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('Define FLASK_SECRET_KEY com pelo menos 32 caracteres aleatórios.')
    if not app.config['AUDIT_HMAC_KEY'] or len(app.config['AUDIT_HMAC_KEY']) < 32:
        raise RuntimeError('Define AUDIT_HMAC_KEY com pelo menos 32 caracteres aleatórios.')
    if not app.config['MFA_ENC_KEY']:
        raise RuntimeError('Define MFA_ENC_KEY com uma chave Fernet válida.')
    if app.config['AUDIT_HMAC_KEY'] == app.config['SECRET_KEY']:
        raise RuntimeError('As chaves de sessão e pseudonimização devem ser independentes.')
    app.extensions['fernet'] = Fernet(app.config['MFA_ENC_KEY'].encode())
    from . import db, security, auth, privacy, admin
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Autentique-se para continuar.'
    app.register_blueprint(auth.bp)
    app.register_blueprint(privacy.bp)
    app.register_blueprint(admin.bp)
    security.init_app(app)
    def handle_error(error):
        message = 'O recurso não está disponível ou não tem permissão para esta operação.'
        if error.code in (400, 409, 429) and error.description != default_exceptions[error.code].description:
            message = error.description
        elif error.code == 405:
            message = 'Este método não é permitido. Utilize o formulário da aplicação.'
        elif error.code == 413:
            message = 'O pedido excede o tamanho permitido.'
        return render_template('error.html', error=error, error_message=message), error.code

    for code in (400, 403, 404, 405, 409, 413, 429, 500):
        app.register_error_handler(code, handle_error)
    return app
