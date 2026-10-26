"""Contador técnico temporário necessário à limitação persistente de tentativas."""

from app.extensions import db


class AuthAttempt(db.Model):
    __tablename__ = "auth_attempts"
    bucket = db.Column(db.Text, primary_key=True, nullable=True)
    attempts = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.Integer, nullable=False)
