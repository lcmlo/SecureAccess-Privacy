"""Extensões partilhadas; nenhuma delas cria uma aplicação independente."""

import sqlite3

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.utils.identifiers import compare_identities
from app.utils.organization_names import compare_organization_names

db = SQLAlchemy()
migrate = Migrate(compare_type=False, render_as_batch=True)
login_manager = LoginManager()
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def configure_sqlite(connection, record):
    if isinstance(connection, sqlite3.Connection):
        connection.create_collation("IDENTITY_NOCASE", compare_identities)
        connection.create_collation("ORGANIZATION_NOCASE", compare_organization_names)
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA secure_delete=ON")
        cursor.close()
