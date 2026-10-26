"""Configuração central, carregada apenas quando a fábrica é chamada."""

import os
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 15}}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_REFRESH_EACH_REQUEST = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    MAX_CONTENT_LENGTH = 32768
    MAX_FORM_MEMORY_SIZE = 32768
    MAX_FORM_PARTS = 50
    LOG_RETENTION_DAYS = 90
    RECEIPT_RETENTION_DAYS = 90
    AUTH_WINDOW_SECONDS = 900
    AUTH_MAX_ATTEMPTS = 5
    WTF_CSRF_TIME_LIMIT = 1800


class DevelopmentConfig(Config):
    SESSION_COOKIE_SECURE = False


class TestingConfig(Config):
    TESTING = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True


def environment_config():
    """As variáveis são lidas depois de carregar .env, sem fixá-las ao importar."""
    database = Path(os.getenv("MFA_DB_PATH") or ROOT / "instance" / "secureaccess.db")
    if not database.is_absolute():
        database = ROOT / database
    values = {
        "SECRET_KEY": os.getenv("FLASK_SECRET_KEY"),
        "MFA_ENC_KEY": os.getenv("MFA_ENC_KEY"),
        "AUDIT_HMAC_KEY": os.getenv("AUDIT_HMAC_KEY"),
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + database.resolve().as_posix(),
    }
    if os.getenv("COOKIE_SECURE") is not None:
        values["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE") == "1"
    return values
