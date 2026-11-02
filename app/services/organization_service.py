"""Catálogo profissional e atribuições; nunca modifica User.role."""

import unicodedata

from flask import session
from flask_login import current_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import BadRequest, Conflict, Forbidden, NotFound

from app.extensions import db
from app.models import Department, JobPosition, User, UserProfile
from app.services.audit_service import audit, now
from app.services.user_service import lock_writes
from app.utils.pseudonymization import user_ref

CATALOG = {
    "Direção": ["Diretor-Geral (CEO)", "Diretor de Tecnologia (CTO)"],
    "Desenvolvimento de Software": [
        "Tech Lead",
        "Engenheiro de Software",
        "Programador Backend",
        "Programador Frontend",
        "Engenheiro DevOps",
        "Engenheiro de Qualidade de Software (QA)",
    ],
    "Dados e Inteligência Artificial": [
        "Analista de Dados",
        "Engenheiro de Dados",
        "Cientista de Dados",
        "Engenheiro de Inteligência Artificial",
    ],
    "Cibersegurança e Privacidade": [
        "Analista de Cibersegurança",
        "Responsável de Segurança da Informação",
        "Responsável de Privacidade",
    ],
    "Produto e Negócio": ["Gestor de Produto", "Analista de Negócio", "Designer UX/UI"],
    "Operações e Administração": [
        "Técnico de Recursos Humanos",
        "Técnico de Suporte Informático",
        "Técnico Financeiro e Administrativo",
    ],
}


def seed_catalog():
    """Uma transação; não reativa, renomeia ou substitui entradas existentes."""
    lock_writes()
    counts = dict(
        departments_created=0,
        departments_existing=0,
        positions_created=0,
        positions_existing=0,
        updated=0,
    )
    try:
        for name, titles in CATALOG.items():
            department = db.session.scalar(db.select(Department).where(Department.name == name))
            if department is None:
                department = Department(name=name)
                db.session.add(department)
                db.session.flush()
                counts["departments_created"] += 1
            else:
                counts["departments_existing"] += 1
            for title in titles:
                position = db.session.scalar(
                    db.select(JobPosition).where(
                        JobPosition.department_id == department.id, JobPosition.name == title
                    )
                )
                if position is None:
                    db.session.add(JobPosition(department_id=department.id, name=title))
                    counts["positions_created"] += 1
                else:
                    counts["positions_existing"] += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return counts


def authorized_write():
    actor_id, version = current_user.id, session.get("version")
    lock_writes()
    actor = db.session.get(User, actor_id, populate_existing=True)
    if (
        not actor
        or not actor.active
        or actor.role != "admin"
        or not actor.mfa_enabled
        or actor.session_version != version
    ):
        raise Forbidden("A sessão já não tem autorização administrativa.")
    return actor_id


def identifier(value, optional=False):
    if optional and value in (None, ""):
        return None
    try:
        result = int(value)
        if result <= 0:
            raise ValueError()
        return result
    except (ValueError, TypeError) as error:
        raise BadRequest("Identificador inválido.") from error


def text_field(value, limit, required=False):
    value = unicodedata.normalize("NFC", " ".join(value.split()))
    if (
        (required and not value)
        or len(value) > limit
        or any(unicodedata.category(c).startswith("C") for c in value)
    ):
        raise BadRequest(
            "Preencha um nome válido (até 120 caracteres) e uma descrição até 1000 caracteres."
        )
    return value or None


def record(model, uid):
    item = db.session.get(model, uid)
    if item is None:
        raise NotFound()
    return item


def commit(event, actor_id, target_id=None):
    audit(event, user_ref(actor_id))
    if target_id is not None and target_id != actor_id:
        audit(event, user_ref(target_id))
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise Conflict(
            "Já existe um departamento com esse nome ou um cargo com esse nome no departamento selecionado."
        ) from error


def save_catalog(kind, uid, values):
    actor_id = authorized_write()
    model = Department if kind == "departments" else JobPosition
    item = record(model, uid) if uid else model()
    prefix = "DEPARTMENT" if model is Department else "JOB_POSITION"
    action = values.get("action", "save")
    if action in ("deactivate", "reactivate"):
        if not uid:
            raise BadRequest("Selecione um registo existente.")
        if action == "reactivate" and model is JobPosition and not item.department.is_active:
            raise Conflict("Reative primeiro o departamento.")
        item.is_active = action == "reactivate"
        event = prefix + ("_REACTIVATED" if item.is_active else "_DEACTIVATED")
    elif action == "save":
        name = text_field(values.get("name", ""), 120, True)
        description = text_field(values.get("description", ""), 1000)
        if model is JobPosition:
            department = record(Department, identifier(values.get("department_id")))
            if not department.is_active:
                raise Conflict("Selecione um departamento ativo.")
            if uid and item.department_id != department.id:
                with db.session.no_autoflush:
                    assigned = db.session.scalar(
                        db.select(func.count())
                        .select_from(UserProfile)
                        .where(UserProfile.job_position_id == uid)
                    )
                if assigned and values.get("confirm_move") != "1":
                    raise Conflict(
                        "Este cargo tem colaboradores associados. Confirme explicitamente a mudança de departamento."
                    )
            item.department_id = department.id
        item.name = name
        item.description = description
        event = prefix + ("_UPDATED" if uid else "_CREATED")
    else:
        raise BadRequest("Operação inválida.")
    item.updated_at = now()
    db.session.add(item)
    commit(event, actor_id)


def assign(uid, values):
    actor_id = authorized_write()
    if values.get("action", "assign") not in ("assign", "remove"):
        raise BadRequest("Operação inválida.")
    target = record(User, uid)
    position_id = identifier(values.get("job_position_id"), optional=True)
    department_id = identifier(values.get("department_id"), optional=True)
    if values.get("action") == "remove":
        position_id = None
    elif position_id is None:
        raise BadRequest("Selecione um departamento e um cargo, ou use Remover atribuição.")
    if position_id is not None:
        position = record(JobPosition, position_id)
        if position.department_id != department_id:
            raise BadRequest("O cargo não pertence ao departamento selecionado.")
        if not position.is_active or not position.department.is_active:
            raise Conflict("O cargo e o departamento têm de estar ativos.")
    if not target.profile:
        target.profile = UserProfile()
    previous = target.profile.job_position_id
    target.profile.job_position_id = position_id
    target.profile.updated_at = now()
    event = (
        "JOB_POSITION_REMOVED"
        if position_id is None
        else ("JOB_POSITION_CHANGED" if previous else "JOB_POSITION_ASSIGNED")
    )
    commit(event, actor_id, uid)


def search_collaborators(filters):
    statement = db.select(User).outerjoin(UserProfile).outerjoin(JobPosition).outerjoin(Department)
    query = filters.get("q", "").strip()[:120]
    if query:
        statement = statement.where(
            or_(
                func.instr(func.lower(User.username), query.lower()) > 0,
                func.instr(func.lower(UserProfile.full_name), query.lower()) > 0,
            )
        )
    role, active = filters.get("role", ""), filters.get("active", "")
    if role not in ("", "user", "admin") or active not in ("", "0", "1"):
        raise BadRequest("Filtro inválido.")
    if role:
        statement = statement.where(User.role == role)
    if active:
        statement = statement.where(User.active == int(active))
    for key, column in (
        ("department_id", JobPosition.department_id),
        ("job_position_id", UserProfile.job_position_id),
    ):
        if filters.get(key):
            statement = statement.where(column == identifier(filters[key]))
    try:
        page = int(filters.get("page", "1"))
        if page < 1:
            raise ValueError()
    except ValueError as error:
        raise BadRequest("Página inválida.") from error
    # Não carregar fotografias, NIF ou morada para a listagem administrativa.
    statement = statement.options(
        selectinload(User.profile)
        .load_only(UserProfile.full_name, UserProfile.job_position_id)
        .selectinload(UserProfile.job_position)
        .selectinload(JobPosition.department)
    )
    return db.paginate(statement.order_by(User.id), page=page, per_page=25, error_out=False)
