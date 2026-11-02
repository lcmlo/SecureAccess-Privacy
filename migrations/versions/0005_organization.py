"""Catálogo profissional relacional; conserva integralmente job_title anterior."""

import sqlalchemy as sa
from alembic import op

revision = "0005_organization"
down_revision = "0004_birth_date"
branch_labels = None
depends_on = None


def upgrade():
    def common():
        return [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120, collation="ORGANIZATION_NOCASE"), nullable=False),
            sa.Column("description", sa.String(1000)),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column(
                "created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
            ),
            sa.Column(
                "updated_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
            ),
        ]

    op.create_table("departments", *common(), sa.UniqueConstraint("name"))
    op.create_table(
        "job_positions",
        *common(),
        sa.Column(
            "department_id",
            sa.Integer(),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("department_id", "name", name="uq_job_position_department_name"),
    )
    op.create_index("ix_job_positions_department_id", "job_positions", ["department_id"])
    with op.batch_alter_table("user_profiles") as batch:
        batch.add_column(sa.Column("job_position_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_profile_job_position",
            "job_positions",
            ["job_position_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_user_profiles_job_position_id", ["job_position_id"])


def downgrade():
    raise RuntimeError("Restaurar o backup para reverter sem perder atribuições profissionais.")
