from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from werkzeug.exceptions import BadRequest, Conflict, Forbidden, NotFound

from app.extensions import db
from app.models import AuditLog, DeletionRequest, User
from app.services.audit_service import audit
from app.utils.pseudonymization import user_ref


def lock_writes():
    """Reserva a escrita SQLite antes de ler invariantes partilhadas."""
    db.session.rollback()
    db.session.execute(db.text("BEGIN IMMEDIATE"))


def user_dashboard(user):
    last = db.session.scalar(
        db.select(AuditLog.event_timestamp)
        .where(
            AuditLog.user_ref == user_ref(user.id),
            AuditLog.event_type == "login",
            AuditLog.result == "sucesso",
        )
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    return [
        (
            "Estado da MFA",
            "Ativa" if user.mfa_enabled else "Inativa",
            "Proteção da conta por dois fatores.",
            "user.data",
        ),
        (
            "Último acesso",
            last + " UTC" if last else "Sem registo conservado",
            "Última autenticação bem-sucedida conservada.",
            "user.history",
        ),
        (
            "Privacidade",
            "Dados minimizados",
            "Registos pseudonimizados e retenção limitada.",
            "privacy.center",
        ),
        (
            "Os meus dados",
            "Consultar e exportar",
            "Aceda às informações associadas à sua conta.",
            "user.data",
        ),
    ]


def admin_dashboard():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    def count(model, *conditions):
        return db.session.scalar(db.select(func.count()).select_from(model).where(*conditions))

    return [
        (
            "Utilizadores ativos",
            count(User, User.active == 1),
            "Contas com acesso autorizado.",
            "admin.users",
        ),
        (
            "Falhas de autenticação",
            count(
                AuditLog,
                AuditLog.result == "falha",
                AuditLog.event_type.in_(["login", "mfa_falha"]),
                AuditLog.event_timestamp >= since,
            ),
            "Nas últimas 24 horas.",
            "admin.logs",
        ),
        (
            "Pedidos pendentes",
            count(DeletionRequest, DeletionRequest.status == "pendente"),
            "A aguardar processamento.",
            "admin.deletions",
        ),
        (
            "MFA ativa",
            count(User, User.active == 1, User.mfa_enabled == 1),
            "Contas ativas com MFA configurada.",
            "admin.users",
        ),
    ]


def search_users(query="", role=""):
    if role not in ("", "user", "admin"):
        raise BadRequest("Perfil inválido.")
    statement = db.select(User).where(func.instr(func.lower(User.username), query[:64].lower()) > 0)
    if role:
        statement = statement.where(User.role == role)
    return db.session.scalars(statement.order_by(User.id).limit(200)).all()


def update_user(actor_id, uid, action):
    if action not in ("activate", "deactivate", "user", "admin") or actor_id == uid:
        raise Forbidden()
    lock_writes()
    target = db.session.get(User, uid)
    if not target:
        raise NotFound()
    if action == "admin" and (not target.mfa_enabled or not target.active):
        raise Conflict("A conta deve estar ativa e ter MFA configurada.")
    if target.role == "admin" and target.active and action in ("deactivate", "user"):
        ensure_other_admin()
    if action in ("user", "admin"):
        target.role, event = action, "perfil_alterado"
    else:
        target.active, event = int(action == "activate"), "conta_alterada"
    target.session_version += 1
    audit(event, user_ref(actor_id))
    audit(event, user_ref(uid))
    db.session.commit()


def ensure_other_admin():
    count = db.session.scalar(
        db.select(func.count()).select_from(User).where(User.role == "admin", User.active == 1)
    )
    if count <= 1:
        raise Conflict("Não pode remover o último administrador ativo.")


def promote_admin(username):
    lock_writes()
    user = db.session.scalar(db.select(User).where(User.username == username))
    if not user or not user.active or not user.mfa_enabled:
        raise BadRequest("É necessária uma conta ativa com MFA configurada.")
    user.role = "admin"
    user.session_version += 1
    audit("perfil_alterado_cli", user_ref(user.id))
    db.session.commit()
