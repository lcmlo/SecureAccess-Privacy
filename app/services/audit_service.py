from datetime import date, datetime, timezone

from flask_login import current_user
from werkzeug.exceptions import BadRequest

from app.extensions import db
from app.models import AuditLog
from app.utils.pseudonymization import user_ref

EVENTS = {
    "registo": "Registo da conta",
    "login": "Login",
    "mfa_falha": "Falha na MFA",
    "mfa_ativada": "MFA ativada",
    "logout": "Logout",
    "exportacao": "Exportação de dados",
    "pedido_eliminacao": "Pedido de eliminação",
    "eliminacao_processamento": "Eliminação em processamento",
    "eliminacao_concluida": "Eliminação concluída",
    "conta_alterada": "Estado da conta alterado",
    "perfil_alterado": "Perfil alterado",
    "perfil_alterado_cli": "Perfil atribuído pela consola",
    "limpeza": "Limpeza de registos",
}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def audit(event, ref=None, result="sucesso"):
    if event not in EVENTS or result not in ("sucesso", "falha"):
        raise ValueError("Evento inválido")
    db.session.add(
        AuditLog(
            user_ref=ref or user_ref(current_user.id),
            event_type=event,
            event_timestamp=now(),
            result=result,
        )
    )


def filtered_logs(filters, ref=None, limit=100):
    query = db.select(AuditLog)
    if ref:
        query = query.where(AuditLog.user_ref == ref)
    for field in ("start", "end"):
        value = filters.get(field, "")
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise BadRequest("Data inválida.") from error
            if field == "start":
                query = query.where(AuditLog.event_timestamp >= value + " 00:00:00")
            else:
                query = query.where(AuditLog.event_timestamp <= value + " 23:59:59")
    for field, allowed in (("event_type", EVENTS), ("result", ("sucesso", "falha"))):
        value = filters.get(field, "")
        if value:
            if value not in allowed:
                raise BadRequest("Filtro inválido.")
            query = query.where(getattr(AuditLog, field) == value)
    try:
        page = max(1, int(filters.get("page", "1")))
    except ValueError as error:
        raise BadRequest("Página inválida.") from error
    return db.session.scalars(
        query.order_by(AuditLog.id.desc()).limit(limit).offset((page - 1) * limit)
    ).all()
