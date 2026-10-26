from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table

from app.extensions import db
from app.models import DeletionRequest
from migrations.schema_compat import include_object


def test_fk_comparator_preserves_real_action_differences(app):
    with app.app_context(), db.engine.connect() as connection:
        actual_fk = next(iter(DeletionRequest.__table__.foreign_key_constraints))
        assert not include_object(
            actual_fk,
            None,
            "foreign_key_constraint",
            False,
            None,
            connection=connection,
            metadata=db.metadata,
        )
        # O SQLite mantém SET NULL; o modelo abaixo propõe CASCADE: mudança real.
        changed = MetaData()
        Table("users", changed, Column("id", Integer, primary_key=True))
        child = Table(
            "deletion_requests",
            changed,
            Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
        )
        changed_fk = next(iter(child.foreign_key_constraints))
        assert include_object(
            changed_fk,
            None,
            "foreign_key_constraint",
            False,
            None,
            connection=connection,
            metadata=changed,
        )
