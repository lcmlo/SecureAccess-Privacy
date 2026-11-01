from sqlalchemy import text

from app.extensions import db
from app.utils.birth_dates import calculate_age


class UserProfile(db.Model):
    __tablename__ = "user_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name = db.Column(db.String(120))
    birth_date = db.Column(db.Date)
    # Histórico anterior à migração: não editável nem usado para calcular a idade.
    legacy_age = db.Column(db.Integer)
    gender = db.Column(db.String(40))
    tax_number = db.Column(db.String(9))
    address = db.Column(db.String(300))
    marital_status = db.Column(db.String(30))
    job_title = db.Column(db.String(120))
    photo = db.Column(db.LargeBinary)
    updated_at = db.Column(db.Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    user = db.relationship("User", back_populates="profile")

    @property
    def age(self):
        return calculate_age(self.birth_date)
