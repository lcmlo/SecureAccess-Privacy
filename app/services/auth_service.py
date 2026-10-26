import re
import time

from flask import current_app, session
from flask_login import login_user, logout_user
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest, Forbidden, TooManyRequests
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import AuthAttempt, User
from app.services.audit_service import audit
from app.services.mfa_service import verify_totp
from app.utils.pseudonymization import pseudonym, user_ref

DUMMY_HASH = generate_password_hash("unavailable-account-password")


def throttle(scope, identity, origin):
    timestamp = int(time.time())
    for key in (f"{scope}:identity:{identity}", f"{scope}:origin:{origin}"):
        bucket = pseudonym(key)
        statement = insert(AuthAttempt).values(
            bucket=bucket,
            attempts=1,
            expires_at=timestamp + current_app.config["AUTH_WINDOW_SECONDS"],
        )
        expired = AuthAttempt.expires_at <= timestamp
        statement = statement.on_conflict_do_update(
            index_elements=["bucket"],
            set_={
                "attempts": db.case((expired, 1), else_=AuthAttempt.attempts + 1),
                "expires_at": db.case(
                    (expired, statement.excluded.expires_at),
                    else_=AuthAttempt.expires_at,
                ),
            },
        ).returning(AuthAttempt.attempts)
        attempts = db.session.execute(statement).scalar_one()
        db.session.commit()
        if attempts > current_app.config["AUTH_MAX_ATTEMPTS"]:
            raise TooManyRequests("Demasiadas tentativas. Aguarde 15 minutos.")


def register(username, password, origin):
    throttle("register", origin or "local", origin)
    username = username.strip()
    if not re.fullmatch(r"[\w.-]{3,64}", username) or not 12 <= len(password) <= 128:
        raise BadRequest(
            "Use um nome de utilizador de 3 a 64 caracteres e uma palavra-passe de 12 a 128 caracteres."
        )
    user = User(username=username, password_hash=generate_password_hash(password), role="user")
    try:
        db.session.add(user)
        db.session.flush()
        audit("registo", user_ref(user.id))
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise BadRequest("Não foi possível criar a conta com os dados indicados.") from error
    return user


def start_login(username, password, origin):
    username = username.strip()
    throttle("login", username.casefold(), origin)
    user = db.session.scalar(db.select(User).where(User.username == username))
    valid = check_password_hash(user.password_hash if user else DUMMY_HASH, password)
    if not user or not user.active or not valid:
        audit(
            "login",
            user_ref(user.id) if user else pseudonym("unknown:" + username),
            "falha",
        )
        db.session.commit()
        return None
    session.clear()
    session["pending_user_id"] = user.id
    session["pending_at"] = time.time()
    session["pending_version"] = user.session_version
    return user


def pending_user():
    uid = session.get("pending_user_id")
    if not uid or time.time() - session.get("pending_at", 0) > 300:
        session.clear()
        return None
    user = db.session.get(User, uid)
    if user and user.active and user.session_version == session.get("pending_version"):
        return user
    session.clear()
    return None


def finish_mfa(user, token, origin, setup=False):
    throttle("mfa", str(user.id), origin)
    if not verify_totp(user, token):
        audit("mfa_falha", user_ref(user.id), "falha")
        db.session.commit()
        return False
    db.session.refresh(user)
    if not user.active or user.session_version != session.get("pending_version"):
        raise Forbidden()
    if setup:
        user.mfa_enabled = 1
        audit("mfa_ativada", user_ref(user.id))
    session.clear()
    session.permanent = True
    session["version"] = user.session_version
    session["authenticated_at"] = time.time()
    login_user(user)
    audit("login", user_ref(user.id))
    db.session.commit()
    return True


def confirm_identity(uid, password, token, origin):
    throttle("confirm", str(uid), origin)
    user = db.session.get(User, uid, populate_existing=True)
    if not user or not user.active or not check_password_hash(user.password_hash, password):
        raise Forbidden("Não foi possível confirmar a identidade.")
    if not verify_totp(user, token):
        raise Forbidden("Código MFA inválido ou já utilizado. Aguarde pelo próximo código.")


def end_session(uid):
    audit("logout", user_ref(uid))
    db.session.commit()
    logout_user()
    session.clear()
