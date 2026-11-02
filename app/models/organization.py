from sqlalchemy import text

from app.extensions import db


class Department(db.Model):
    __tablename__ = "departments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120, collation="ORGANIZATION_NOCASE"), nullable=False, unique=True)
    description = db.Column(db.String(1000))
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=text("1"))
    created_at = db.Column(db.Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    positions = db.relationship("JobPosition", back_populates="department")


class JobPosition(db.Model):
    __tablename__ = "job_positions"
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name = db.Column(db.String(120, collation="ORGANIZATION_NOCASE"), nullable=False)
    description = db.Column(db.String(1000))
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=text("1"))
    created_at = db.Column(db.Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    department = db.relationship("Department", back_populates="positions")
    __table_args__ = (
        db.UniqueConstraint("department_id", "name", name="uq_job_position_department_name"),
    )
