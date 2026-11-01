"""Perfis pessoais opcionais, sem alterar as contas existentes."""

import sqlalchemy as sa
from alembic import op

revision = "0002_user_profiles"
down_revision = "0001_privacy"
branch_labels = None
depends_on = None


def upgrade():
    profiles = op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("full_name", sa.String(120)),
        sa.Column("updated_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.execute(profiles.insert().from_select(["user_id"], sa.select(sa.column("id")).select_from(sa.table("users"))))


def downgrade():
    raise RuntimeError("O perfil contém dados pessoais: restaurar um backup para reverter a migração.")
