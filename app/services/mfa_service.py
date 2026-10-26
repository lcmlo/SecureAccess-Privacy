import base64
import io
import re
import time

import pyotp
import qrcode
from cryptography.fernet import InvalidToken
from flask import current_app

from app.extensions import db
from app.models import User


def decrypt(ciphertext):
    return current_app.extensions["fernet"].decrypt(ciphertext.encode()).decode()


def verify_totp(user, token):
    if not re.fullmatch(r"[0-9]{6}", token) or not user.totp_secret:
        return False
    try:
        secret = decrypt(user.totp_secret)
    except InvalidToken:
        return False
    timestamp = time.time()
    step = int(timestamp) // 30
    if not pyotp.TOTP(secret).verify(token, for_time=timestamp, valid_window=0):
        return False
    changed = db.session.execute(
        db.update(User)
        .where(
            User.id == user.id,
            User.active == 1,
            db.or_(User.last_totp_step.is_(None), User.last_totp_step < step),
        )
        .values(last_totp_step=step)
    ).rowcount
    db.session.commit()
    return changed == 1


def setup_material(user):
    if user.mfa_enabled:
        raise ValueError("A MFA já está configurada.")
    if not user.totp_secret:
        ciphertext = (
            current_app.extensions["fernet"].encrypt(pyotp.random_base32().encode()).decode()
        )
        # Evita substituir uma chave gerada por um pedido concorrente.
        db.session.execute(
            db.update(User)
            .where(User.id == user.id, User.totp_secret.is_(None))
            .values(totp_secret=ciphertext)
        )
        db.session.commit()
        db.session.refresh(user)
    secret = decrypt(user.totp_secret)
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.username, issuer_name="SecureAccess Privacy"
    )
    buffer = io.BytesIO()
    qrcode.make(uri).save(buffer, format="PNG")
    return {"secret": secret, "qr_b64": base64.b64encode(buffer.getvalue()).decode()}
