"""Migrações Flask-Migrate com backup automático antes de alterar SQLite."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from alembic import context
from flask import current_app

from migrations.schema_compat import include_object

config = context.config
database = current_app.extensions["migrate"].db
target_metadata = database.metadata


def run_migrations_offline():
    context.configure(
        url=str(database.engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=False,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = database.engine
    filename = engine.url.database
    if (
        filename
        and filename != ":memory:"
        and Path(filename).exists()
        and Path(filename).stat().st_size
    ):
        source = Path(filename)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        destination = source.with_name(source.name + f".{stamp}.pre-alembic.bak")
        with (
            closing(sqlite3.connect(source)) as original,
            closing(sqlite3.connect(destination)) as backup,
        ):
            original.backup(backup)
    with engine.connect() as connection:
        # DDL SQLite fica na mesma transação que o registo da revisão Alembic.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=False,
            render_as_batch=True,
            include_object=partial(include_object, connection=connection, metadata=target_metadata),
        )
        try:
            context.run_migrations()
            connection.commit()
        except Exception:
            connection.rollback()
            raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
