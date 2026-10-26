"""Adota o esquema legado ou inicializa uma base nova sem recriar contas.

Revision ID: 0001_privacy
Revises: nenhuma
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_privacy"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("username", sa.Text, nullable=False, unique=True),
            sa.Column("password_hash", sa.Text, nullable=False),
            sa.Column("totp_secret", sa.Text),
            sa.Column("mfa_enabled", sa.Integer, server_default="0"),
            sa.Column("created_at", sa.Text, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("role", sa.Text, nullable=False, server_default="user"),
            sa.Column("active", sa.Integer, nullable=False, server_default="1"),
            sa.Column("session_version", sa.Integer, nullable=False, server_default="0"),
            sa.Column("last_totp_step", sa.Integer),
            sa.CheckConstraint("role IN ('user','admin')", name="ck_users_role"),
            sa.CheckConstraint("active IN (0,1)", name="ck_users_active"),
            sqlite_autoincrement=True,
        )
    else:
        columns = {item["name"] for item in inspector.get_columns("users")}
        additions = [
            sa.Column(
                "role",
                sa.Text,
                sa.CheckConstraint("role IN ('user','admin')", name="ck_users_role"),
                nullable=False,
                server_default="user",
            ),
            sa.Column(
                "active",
                sa.Integer,
                sa.CheckConstraint("active IN (0,1)", name="ck_users_active"),
                nullable=False,
                server_default="1",
            ),
            sa.Column("session_version", sa.Integer, nullable=False, server_default="0"),
            sa.Column("last_totp_step", sa.Integer),
        ]
        for column in additions:
            if column.name not in columns:
                op.add_column("users", column)
    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_ref", sa.Text, nullable=False),
            sa.Column("event_type", sa.Text, nullable=False),
            sa.Column("event_timestamp", sa.Text, nullable=False),
            sa.Column("result", sa.Text, nullable=False),
            sa.CheckConstraint("result IN ('sucesso','falha')", name="ck_audit_result"),
            sqlite_autoincrement=True,
        )
    if "deletion_requests" not in tables:
        op.create_table(
            "deletion_requests",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("requested_at", sa.Text, nullable=False),
            sa.Column("status", sa.Text, nullable=False, server_default="pendente"),
            sa.Column("completed_at", sa.Text),
            sa.CheckConstraint(
                "status IN ('pendente','em processamento','concluído')",
                name="ck_deletion_status",
            ),
            sa.CheckConstraint(
                "(status='concluído' AND completed_at IS NOT NULL) OR "
                "(status!='concluído' AND completed_at IS NULL)",
                name="ck_deletion_completed",
            ),
            sqlite_autoincrement=True,
        )
    if "deletion_history" not in tables:
        op.create_table(
            "deletion_history",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "request_id",
                sa.Integer,
                sa.ForeignKey("deletion_requests.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.Text, nullable=False),
            sa.Column("changed_at", sa.Text, nullable=False),
            sqlite_autoincrement=True,
        )
    if "auth_attempts" not in tables:
        op.create_table(
            "auth_attempts",
            sa.Column("bucket", sa.Text, primary_key=True, nullable=True),
            sa.Column("attempts", sa.Integer, nullable=False),
            sa.Column("expires_at", sa.Integer, nullable=False),
        )
    inspector = sa.inspect(op.get_bind())
    for table, name, columns, options in [
        ("audit_logs", "audit_ref_time", ["user_ref", "event_timestamp"], {}),
        ("audit_logs", "audit_time", ["event_timestamp"], {}),
        (
            "deletion_requests",
            "one_open_request",
            ["user_id"],
            {"unique": True, "sqlite_where": sa.text("status!='concluído'")},
        ),
    ]:
        if name not in {index["name"] for index in inspector.get_indexes(table)}:
            op.create_index(name, table, columns, **options)


def downgrade():
    raise RuntimeError(
        "Migração de adoção não destrutiva: restaurar o backup para regressar ao esquema anterior."
    )
