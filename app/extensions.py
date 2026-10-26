"""Extensões partilhadas; nenhuma delas cria uma aplicação independente."""

import sqlite3

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate(compare_type=False, render_as_batch=True)
login_manager = LoginManager()
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def configure_sqlite(connection, record):
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA secure_delete=ON")
        cursor.close()
