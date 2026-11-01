"""Email único e extensão facultativa do perfil académico; preserva contas."""

import sqlalchemy as sa
from alembic import op

from app.utils.identifiers import identity_key, normalize_email

revision = "0003_registration_profile"
down_revision = "0002_user_profiles"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("users")}
    # Verifica todos os conflitos antes de executar qualquer alteração de esquema.
    for field in ("username", "email"):
        if field not in columns:
            continue
        groups = {}
        for uid, value in connection.execute(sa.text(f"SELECT id, {field} FROM users")):
            if value is None:
                continue
            key = identity_key(normalize_email(value) if field == "email" else value)
            groups.setdefault(key, []).append(uid)
        conflicts = [ids for ids in groups.values() if len(ids) > 1]
        if conflicts:
            raise RuntimeError(f"Migração interrompida: conflitos de {field} nos IDs {conflicts}. Resolver manualmente; nenhuma conta foi alterada.")
    if "email" not in columns:
        op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.create_index("uq_users_username_ci", "users", [sa.text("username COLLATE IDENTITY_NOCASE")], unique=True)
    op.create_index("uq_users_email_ci", "users", [sa.text("email COLLATE IDENTITY_NOCASE")], unique=True)
    for column in (
        sa.Column("age", sa.Integer), sa.Column("gender", sa.String(40)),
        sa.Column("tax_number", sa.String(9)), sa.Column("address", sa.String(300)),
        sa.Column("marital_status", sa.String(30)), sa.Column("job_title", sa.String(120)),
        sa.Column("photo", sa.LargeBinary),
    ):
        op.add_column("user_profiles", column)


def downgrade():
    raise RuntimeError("Restaurar um backup para reverter sem perder dados pessoais.")
