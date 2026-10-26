from flask_login import UserMixin
from sqlalchemy import CheckConstraint, text

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user','admin')", name="ck_users_role"),
        CheckConstraint("active IN (0,1)", name="ck_users_active"),
        {"sqlite_autoincrement": True},
    )
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text, nullable=False, unique=True)
    password_hash = db.Column(db.Text, nullable=False)
    totp_secret = db.Column(db.Text)
    mfa_enabled = db.Column(db.Integer, default=0, server_default=text("0"))
    created_at = db.Column(db.Text, server_default=text("CURRENT_TIMESTAMP"))
    role = db.Column(db.Text, nullable=False, default="user", server_default="user")
    active = db.Column(db.Integer, nullable=False, default=1, server_default=text("1"))
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default=text("0"))
    last_totp_step = db.Column(db.Integer)

    @property
    def is_active(self):
        return bool(self.active)

    def public_data(self):
        """Lista positiva: os segredos nunca são serializados por introspeção."""
        return {
            key: getattr(self, key)
            for key in ("id", "username", "role", "mfa_enabled", "created_at", "active")
        }
