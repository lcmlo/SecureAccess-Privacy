import csv
import io
import json

from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest, Conflict, Forbidden, NotFound

from app.extensions import db
from app.models import AuditLog, AuthAttempt, DeletionHistory, DeletionRequest, User
from app.services.audit_service import audit, now
from app.services.user_service import ensure_other_admin, lock_writes
from app.utils.pseudonymization import pseudonym, user_ref


def export_data(uid, categories, fmt):
    if (
        not categories
        or not set(categories) <= {"account", "history", "requests"}
        or fmt not in ("json", "csv")
    ):
        raise BadRequest("Selecione categorias e formato válidos.")
    user = db.session.get(User, uid)
    if not user:
        raise NotFound()
    payload = {}
    if "account" in categories:
        payload["account"] = user.public_data()
    if "history" in categories:
        logs = db.session.scalars(
            db.select(AuditLog).where(AuditLog.user_ref == user_ref(uid)).order_by(AuditLog.id)
        ).all()
        payload["history"] = [log.personal_data() for log in logs]
    if "requests" in categories:
        payload["requests"] = [item.personal_data() for item in own_requests(uid)]
    audit("exportacao", user_ref(uid))
    db.session.commit()
    if fmt == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["categoria", "registo", "campo", "valor"])
    for category, values in payload.items():
        for index, record in enumerate(values if isinstance(values, list) else [values], 1):
            for key, value in record.items():
                text = "" if value is None else str(value)
                if text.lstrip().startswith(("=", "+", "-", "@")):
                    text = "'" + text
                writer.writerow([category, index, key, text])
    return "\ufeff" + buffer.getvalue(), "text/csv"


def own_requests(uid):
    return db.session.scalars(
        db.select(DeletionRequest)
        .where(DeletionRequest.user_id == uid)
        .order_by(DeletionRequest.id.desc())
    ).all()


def create_deletion_request(uid):
    try:
        item = DeletionRequest(user_id=uid, requested_at=now(), status="pendente")
        item.history.append(DeletionHistory(status="pendente", changed_at=now()))
        db.session.add(item)
        audit("pedido_eliminacao", user_ref(uid))
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def list_requests():
    return db.session.scalars(
        db.select(DeletionRequest).order_by(DeletionRequest.id.desc()).limit(200)
    ).all()


def process_request(actor_id, rid, action):
    if action not in ("process", "complete"):
        raise BadRequest("Operação inválida.")
    lock_writes()
    item = db.session.get(DeletionRequest, rid)
    if not item:
        raise NotFound()
    if item.user_id == actor_id:
        raise Forbidden("Outro administrador deve tratar o seu pedido.")
    if action == "process" and item.status == "pendente":
        status, event = "em processamento", "eliminacao_processamento"
        item.status = status
        audit(event, user_ref(item.user_id))
    elif action == "complete" and item.status == "em processamento":
        target = db.session.get(User, item.user_id)
        if not target:
            raise Conflict("A conta associada já não está disponível.")
        if target.role == "admin" and target.active:
            ensure_other_admin()
        status, event = "concluído", "eliminacao_concluida"
        db.session.execute(db.delete(AuditLog).where(AuditLog.user_ref == user_ref(target.id)))
        buckets = [
            pseudonym(value)
            for value in (
                f"login:identity:{target.username.casefold()}",
                f"mfa:identity:{target.id}",
                f"confirm:identity:{target.id}",
            )
        ]
        db.session.execute(db.delete(AuthAttempt).where(AuthAttempt.bucket.in_(buckets)))
        item.status, item.completed_at, item.user_id = status, now(), None
        db.session.flush()
        db.session.delete(target)
    else:
        raise Conflict("Transição de estado inválida.")
    item.history.append(DeletionHistory(status=status, changed_at=now()))
    audit(event, user_ref(actor_id))
    db.session.commit()
