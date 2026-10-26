"""Leitura SQLite independente, usada apenas nas verificações de regressão."""

import sqlite3

from flask import current_app, g
from sqlalchemy.engine import make_url


def get_db():
    if "inspection_db" not in g:
        path = make_url(current_app.config["SQLALCHEMY_DATABASE_URI"]).database
        g.inspection_db = sqlite3.connect(path)
        g.inspection_db.row_factory = sqlite3.Row
        g.inspection_db.execute("PRAGMA foreign_keys=ON")
    return g.inspection_db
