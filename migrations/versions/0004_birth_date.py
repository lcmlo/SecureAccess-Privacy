"""Data de nascimento facultativa, preservando idades históricas sem conversão."""

import sqlalchemy as sa
from alembic import op

revision = "0004_birth_date"
down_revision = "0003_registration_profile"
branch_labels = None
depends_on = None


def upgrade():
    # RENAME COLUMN conserva os valores e não recria tabelas ou contas SQLite.
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE user_profiles RENAME COLUMN age TO legacy_age")
    else:
        op.alter_column("user_profiles", "age", new_column_name="legacy_age", existing_type=sa.Integer())
    op.add_column("user_profiles", sa.Column("birth_date", sa.Date(), nullable=True))


def downgrade():
    raise RuntimeError("Restaurar um backup para reverter sem perder datas de nascimento.")
