import re
import unicodedata

from flask import session
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest

from app.extensions import db
from app.models import User, UserProfile
from app.services.audit_service import audit, now
from app.utils.birth_dates import parse_birth_date
from app.utils.identifiers import EMAIL_TAKEN, USERNAME_TAKEN, normalize_email
from app.utils.pseudonymization import user_ref

PERSONAL_FIELDS = ("birth_date", "gender", "tax_number", "address", "marital_status")
GENDERS = {"feminino", "masculino", "nao_binario", "outro", "prefiro_nao_indicar"}
MARITAL_STATUSES = {"solteiro", "casado", "uniao_facto", "divorciado", "viuvo", "outro"}


def check_available(username, email, uid=None):
    for field, value, message in (("username", username, USERNAME_TAKEN), ("email", email, EMAIL_TAKEN)):
        if value is None:
            continue
        statement = db.select(User.id).where(getattr(User, field).collate("IDENTITY_NOCASE") == value)
        if uid is not None:
            statement = statement.where(User.id != uid)
        if db.session.scalar(statement) is not None:
            raise BadRequest(message)


def duplicate_error(error):
    return BadRequest(EMAIL_TAKEN if "email" in str(error.orig).lower() else USERNAME_TAKEN)


def validate_details(values):
    result = {}
    for field, limit in (("gender", 40), ("tax_number", 9), ("address", 300), ("marital_status", 30)):
        value = values.get(field, "").strip()
        if len(value) > limit or any(unicodedata.category(char).startswith("C") for char in value):
            raise BadRequest("Um dos campos pessoais excede o limite ou contém caracteres inválidos.")
        result[field] = value or None
    result["birth_date"] = parse_birth_date(values.get("birth_date", ""))
    if result["gender"] and result["gender"] not in GENDERS:
        raise BadRequest("Selecione uma opção de género válida.")
    if result["marital_status"] and result["marital_status"] not in MARITAL_STATUSES:
        raise BadRequest("Selecione uma opção de estado civil válida.")
    nif = result["tax_number"]
    if nif:
        if not re.fullmatch(r"[0-9]{9}", nif):
            raise BadRequest("O NIF deve conter nove algarismos.")
        check = 11 - sum(int(digit) * weight for digit, weight in zip(nif[:8], range(9, 1, -1))) % 11
        if int(nif[-1]) != (0 if check >= 10 else check):
            raise BadRequest("O NIF não é válido.")
    return result


def validate_profile(username, full_name):
    username = username.strip()
    full_name = full_name.strip()
    if not re.fullmatch(r"[\w.-]{3,64}", username):
        raise BadRequest("Use um nome de utilizador de 3 a 64 caracteres: letras, números, ponto, hífen ou sublinhado.")
    if len(full_name) > 120 or any(unicodedata.category(char).startswith("C") for char in full_name):
        raise BadRequest("O nome completo deve ter até 120 caracteres e não pode conter caracteres de controlo.")
    return username, full_name or None


def update_profile(username, full_name, email=None, details=None, photo=None, remove_photo=False):
    """A conta a alterar é sempre a da sessão; não aceita IDs nem permissões."""
    username, full_name = validate_profile(username, full_name)
    user = db.session.get(User, current_user.id)
    if email is not None:
        email = normalize_email(email) if email.strip() or user.email else None
    else:
        email = user.email
    check_available(username, email, user.id)
    if not user.profile:
        user.profile = UserProfile()
    changed = user.username != username or user.email != email or user.profile.full_name != full_name
    sensitive_changed = user.username != username or user.email != email
    if sensitive_changed:
        user.session_version += 1
    user.username = username
    user.email = email
    user.profile.full_name = full_name
    if details is not None:
        for field, value in validate_details(details).items():
            changed = changed or getattr(user.profile, field) != value
            setattr(user.profile, field, value)
    if photo is not None or remove_photo:
        new_photo = None if remove_photo else photo
        changed = changed or user.profile.photo != new_photo
        user.profile.photo = new_photo
    if changed:
        user.profile.updated_at = now()
        audit("dados_pessoais_alterados", user_ref(user.id))
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise duplicate_error(error) from error
    if sensitive_changed:
        session["version"] = user.session_version
