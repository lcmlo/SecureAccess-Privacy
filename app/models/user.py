from flask_login import UserMixin
from sqlalchemy import CheckConstraint, text

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text, nullable=False, unique=True)
    email = db.Column(db.String(254))
    __table_args__ = (
        CheckConstraint("role IN ('user','admin')", name="ck_users_role"),
        CheckConstraint("active IN (0,1)", name="ck_users_active"),
        db.Index("uq_users_username_ci", username.collate("IDENTITY_NOCASE"), unique=True),
        db.Index("uq_users_email_ci", email.collate("IDENTITY_NOCASE"), unique=True),
        {"sqlite_autoincrement": True},
    )
    password_hash = db.Column(db.Text, nullable=False)
    totp_secret = db.Column(db.Text)
    mfa_enabled = db.Column(db.Integer, default=0, server_default=text("0"))
    created_at = db.Column(db.Text, server_default=text("CURRENT_TIMESTAMP"))
    role = db.Column(db.Text, nullable=False, default="user", server_default="user")
    active = db.Column(db.Integer, nullable=False, default=1, server_default=text("1"))
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default=text("0"))
    last_totp_step = db.Column(db.Integer)
    profile = db.relationship(
        "UserProfile", back_populates="user", uselist=False,
        cascade="all, delete-orphan", single_parent=True,
    )

    @property
    def is_active(self):
        return bool(self.active)

    def public_data(self):
        """Lista positiva: os segredos nunca são serializados por introspeção."""
        data = {
            key: getattr(self, key)
            for key in ("id", "username", "role", "mfa_enabled", "created_at", "active")
        }
        data["full_name"] = self.profile.full_name if self.profile else None
        data["profile_updated_at"] = self.profile.updated_at if self.profile else None
        data["email"] = self.email
        for field in ("age", "gender", "tax_number", "address", "marital_status", "job_title"):
            data[field] = getattr(self.profile, field) if self.profile else None
        data["birth_date"] = self.profile.birth_date.isoformat() if self.profile and self.profile.birth_date else None
        if self.profile and self.profile.legacy_age is not None:
            data["legacy_age"] = self.profile.legacy_age
        data["photo_available"] = bool(self.profile and self.profile.photo)
        return data
