"""Única fábrica Flask do SecureAccess Privacy."""

import os

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from flask import Flask, session

from app.config import (
    ROOT,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    environment_config,
)
from app.extensions import csrf, db, login_manager, migrate


def create_app(config=None):
    load_dotenv(ROOT / ".env")
    app = Flask(__name__, instance_path=str(ROOT / "instance"), instance_relative_config=True)
    profiles = {
        "development": DevelopmentConfig,
        "testing": TestingConfig,
        "production": ProductionConfig,
    }
    profile = os.getenv("APP_ENV", "development")
    app.config.from_object(profiles[profile])
    app.config.update(environment_config())
    if config:
        app.config.update(config)
    if len(app.config.get("SECRET_KEY") or "") < 32:
        raise RuntimeError("Define FLASK_SECRET_KEY com pelo menos 32 caracteres aleatórios.")
    if len(app.config.get("AUDIT_HMAC_KEY") or "") < 32:
        raise RuntimeError("Define AUDIT_HMAC_KEY com pelo menos 32 caracteres aleatórios.")
    if app.config["SECRET_KEY"] == app.config["AUDIT_HMAC_KEY"]:
        raise RuntimeError("As chaves de sessão e pseudonimização devem ser independentes.")
    if not app.config.get("MFA_ENC_KEY"):
        raise RuntimeError("Define MFA_ENC_KEY com uma chave Fernet válida.")
    if profile == "production" and not app.config["SESSION_COOKIE_SECURE"]:
        raise RuntimeError("A produção exige cookies Secure e HTTPS.")
    os.makedirs(app.instance_path, exist_ok=True)
    app.extensions["fernet"] = Fernet(app.config["MFA_ENC_KEY"].encode())
    db.init_app(app)
    from app import models

    migrate.init_app(app, db, directory=str(ROOT / "migrations"))
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Autentique-se para continuar."

    @login_manager.user_loader
    def load_user(uid):
        try:
            user = db.session.get(models.User, int(uid))
        except (TypeError, ValueError):
            return None
        if user and user.active and user.session_version == session.get("version"):
            return user
        return None

    from app.cli import register_commands
    from app.routes import register_blueprints
    from app.utils.web_security import init_app

    register_blueprints(app)
    init_app(app)
    csrf.init_app(app)
    register_commands(app)
    return app
