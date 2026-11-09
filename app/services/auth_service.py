import re
import time

from flask import current_app, session
from flask_login import login_user, logout_user
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest, Forbidden, TooManyRequests
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import AuthAttempt, User, UserProfile
from app.services.audit_service import audit
from app.services.mfa_service import verify_totp
from app.services.profile_service import check_available, duplicate_error, validate_profile
from app.utils.identifiers import normalize_email
from app.utils.pseudonymization import pseudonym, user_ref

DUMMY_HASH = generate_password_hash("unavailable-account-password")


def _counter_key(category, identity):
    """Buckets distintos dos antigos, sem guardar IPs, usernames ou IDs em claro."""
    return pseudonym(f"auth:v2:{category}:{identity}")


def _increment_counter(category, identity):
    """Incremento atómico em SQLite com janela fixa de AUTH_WINDOW_SECONDS."""
    timestamp = int(time.time())
    statement = insert(AuthAttempt).values(
        bucket=_counter_key(category, identity),
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
    return attempts


def _limit_origin(origin, *, registration=False):
    """Conta TODOS os pedidos de autenticação, mesmo os bem-sucedidos."""
    origin = origin or "unknown"
    count = _increment_counter("requests:origin", origin)
    if count > current_app.config["AUTH_ORIGIN_MAX_REQUESTS"]:
        raise TooManyRequests("Demasiados pedidos de autenticação. Aguarde 15 minutos.")

    # Mantém a proteção mais restritiva que já existia para novos registos.
    if registration:
        count = _increment_counter("requests:register:origin", origin)
        if count > current_app.config["AUTH_REGISTER_MAX_REQUESTS"]:
            raise TooManyRequests("Demasiados pedidos de registo. Aguarde 15 minutos.")


def _failure_identity(user, *, username=None, uid=None):
    if user is not None:
        return f"user:{user.id}"
    if username is not None:
        return f"unknown-username:{username.casefold()}"
    return f"unknown-id:{uid}"


def _check_failure_limit(identity):
    """Bloqueia pedidos posteriores à quinta falha ainda válida."""
    counter = db.session.get(AuthAttempt, _counter_key("failures:identity", identity))
    if (
        counter is not None
        and counter.expires_at > int(time.time())
        and counter.attempts >= current_app.config["AUTH_MAX_ATTEMPTS"]
    ):
        raise TooManyRequests("Demasiadas falhas de autenticação. Aguarde 15 minutos.")


def _record_failure(identity):
    """Regista só uma credencial/código inválido; não conta sucessos."""
    count = _increment_counter("failures:identity", identity)
    # Protege também de verificações concorrentes que passaram o pré-check.
    if count > current_app.config["AUTH_MAX_ATTEMPTS"]:
        raise TooManyRequests("Demasiadas falhas de autenticação. Aguarde 15 minutos.")


def _clear_failures(identity):
    """Chamada apenas após MFA completa ou confirmação de identidade bem-sucedida."""
    db.session.execute(
        db.delete(AuthAttempt).where(
            AuthAttempt.bucket == _counter_key("failures:identity", identity)
        )
    )


def register(username, password, origin, email=""):
    _limit_origin(origin, registration=True)
    username, _ = validate_profile(username, "")
    email = normalize_email(email)
    if not re.fullmatch(r"[\w.-]{3,64}", username) or not 12 <= len(password) <= 128:
        raise BadRequest(
            "Use um nome de utilizador de 3 a 64 caracteres e uma palavra-passe de 12 a 128 caracteres."
        )
    check_available(username, email)
    user = User(username=username, email=email, password_hash=generate_password_hash(password), role="user")
    user.profile = UserProfile()
    try:
        db.session.add(user)
        db.session.flush()
        audit("registo", user_ref(user.id))
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise duplicate_error(error) from error
    return user


def start_login(username, password, origin):
    username = username.strip()
    _limit_origin(origin)
    user = db.session.scalar(db.select(User).where(User.username.collate("IDENTITY_NOCASE") == username))
    identity = _failure_identity(user, username=username)
    _check_failure_limit(identity)
    valid = check_password_hash(user.password_hash if user else DUMMY_HASH, password)
    if not user or not user.active or not valid:
        _record_failure(identity)
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
    _limit_origin(origin)
    identity = _failure_identity(user)
    _check_failure_limit(identity)
    if not verify_totp(user, token):
        _record_failure(identity)
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
    _clear_failures(identity)
    db.session.commit()
    return True


def confirm_identity(uid, password, token, origin):
    _limit_origin(origin)
    user = db.session.get(User, uid, populate_existing=True)
    identity = _failure_identity(user, uid=uid)
    _check_failure_limit(identity)
    if not user or not user.active or not check_password_hash(user.password_hash, password):
        _record_failure(identity)
        raise Forbidden("Não foi possível confirmar a identidade.")
    if not verify_totp(user, token):
        _record_failure(identity)
        raise Forbidden("Código MFA inválido ou já utilizado. Aguarde pelo próximo código.")
    _clear_failures(identity)
    db.session.commit()


def end_session(uid):
    audit("logout", user_ref(uid))
    db.session.commit()
    logout_user()
    session.clear()
