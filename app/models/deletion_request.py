from sqlalchemy import CheckConstraint, Index, text

from app.extensions import db


class DeletionRequest(db.Model):
    __tablename__ = "deletion_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pendente','em processamento','concluído')",
            name="ck_deletion_status",
        ),
        CheckConstraint(
            "(status='concluído' AND completed_at IS NOT NULL) OR "
            "(status!='concluído' AND completed_at IS NULL)",
            name="ck_deletion_completed",
        ),
        Index(
            "one_open_request",
            "user_id",
            unique=True,
            sqlite_where=text("status!='concluído'"),
        ),
        {"sqlite_autoincrement": True},
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    requested_at = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default="pendente", server_default="pendente")
    completed_at = db.Column(db.Text)
    history = db.relationship(
        "DeletionHistory",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DeletionHistory.id",
        lazy="selectin",
    )

    def personal_data(self):
        return {key: getattr(self, key) for key in ("id", "requested_at", "status", "completed_at")}


class DeletionHistory(db.Model):
    __tablename__ = "deletion_history"
    __table_args__ = {"sqlite_autoincrement": True}
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey("deletion_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = db.Column(db.Text, nullable=False)
    changed_at = db.Column(db.Text, nullable=False)
