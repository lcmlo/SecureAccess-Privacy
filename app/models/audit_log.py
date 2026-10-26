from sqlalchemy import CheckConstraint, Index

from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("result IN ('sucesso','falha')", name="ck_audit_result"),
        Index("audit_ref_time", "user_ref", "event_timestamp"),
        Index("audit_time", "event_timestamp"),
        {"sqlite_autoincrement": True},
    )
    id = db.Column(db.Integer, primary_key=True)
    user_ref = db.Column(db.Text, nullable=False)
    event_type = db.Column(db.Text, nullable=False)
    event_timestamp = db.Column(db.Text, nullable=False)
    result = db.Column(db.Text, nullable=False)

    def personal_data(self):
        return {key: getattr(self, key) for key in ("event_type", "event_timestamp", "result")}
