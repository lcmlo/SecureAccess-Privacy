from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from werkzeug.exceptions import BadRequest, HTTPException

from app.extensions import db
from app.models import User
from app.services import audit_service, privacy_service, retention_service, user_service
from app.utils.decorators import admin_required
from app.utils.forms import confirm_form_identity
from app.utils.pseudonymization import user_ref

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@admin_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        title="Dashboard",
        cards=user_service.admin_dashboard(),
        logs=audit_service.filtered_logs(request.args, limit=5),
        administrative=True,
    )


@bp.route("/users")
@admin_required
def users():
    return render_template(
        "admin/users.html",
        title="Utilizadores",
        users=user_service.search_users(request.args.get("q", ""), request.args.get("role", "")),
    )


@bp.route("/users/<int:uid>", methods=["POST"])
@admin_required
def update_user(uid):
    action = request.form.get("action")
    if action not in ("activate", "deactivate", "user", "admin") or uid == current_user.id:
        abort(403)
    if action in ("user", "admin"):
        return perform_role_change(uid)
    actor_version = session.get("version")
    confirm_form_identity()
    user_service.update_user(current_user.id, uid, action, actor_version=actor_version)
    flash("Conta atualizada. Sessões anteriores revogadas.")
    return redirect(url_for("admin.users"))


@bp.route("/logs")
@admin_required
def logs():
    return render_template(
        "admin/audit_logs.html",
        title="Logs de autenticação",
        logs=audit_service.filtered_logs(request.args),
        administrative=True,
    )


@bp.route("/deletions")
@admin_required
def deletions():
    rows = privacy_service.list_requests()
    return render_template(
        "admin/deletion_requests.html",
        title="Pedidos de eliminação",
        requests=rows,
        histories={row.id: row.history for row in rows},
        user_ref=user_ref,
    )


@bp.route("/deletions/<int:rid>", methods=["POST"])
@admin_required
def process_deletion(rid):
    confirm_form_identity()
    privacy_service.process_request(current_user.id, rid, request.form.get("action"))
    flash("Pedido atualizado. A conclusão executa a eliminação na mesma transação.")
    return redirect(url_for("admin.deletions"))


@bp.route("/permissions")
@admin_required
def permissions():
    return render_template(
        "admin/permissions.html", title="Perfis e permissões",
        users=user_service.search_users(request.args.get("q", ""), request.args.get("role", ""), include_names=True),
    )


@bp.route("/permissions/<int:uid>", methods=["GET", "POST"])
@admin_required
def change_role(uid):
    return perform_role_change(uid)


def perform_role_change(uid):
    """Um único fluxo, incluindo os pedidos enviados pela antiga gestão de contas."""
    target = db.session.get(User, uid)
    if not target:
        abort(404)
    action = request.form.get("action") if request.method == "POST" else request.args.get("action")
    if action not in ("user", "admin"):
        abort(400, "Selecione um perfil válido.")
    error_message, status = None, 200
    if request.method == "POST":
        try:
            if request.form.get("confirmation") != "ALTERAR":
                raise BadRequest("Confirme explicitamente a alteração das permissões.")
            expected_role = request.form.get("expected_role")
            if expected_role not in ("user", "admin"):
                raise BadRequest("Reabra a confirmação da alteração de permissões.")
            try:
                target_version = int(request.form.get("target_version", ""))
            except ValueError as error:
                raise BadRequest("Reabra a confirmação da alteração de permissões.") from error
            actor_version = session.get("version")
            confirm_form_identity()
            user_service.update_user(
                current_user.id, uid, action, actor_version=actor_version,
                expected_role=expected_role, target_version=target_version,
            )
        except HTTPException as error:
            db.session.rollback()
            if current_user.role != "admin" or not current_user.active or current_user.session_version != session.get("version"):
                abort(403)
            user_service.audit_role_denied(current_user.id, uid)
            target = db.session.get(User, uid)
            if not target:
                abort(404)
            error_message, status = error.description, error.code
        else:
            message = "As permissões administrativas foram atribuídas com sucesso." if action == "admin" else "As permissões administrativas foram removidas com sucesso."
            flash(message, "success")
            return redirect(url_for("admin.permissions"))
    elif uid == current_user.id:
        abort(403)
    return render_template(
        "admin/role_confirmation.html", title="Confirmar alteração de permissões",
        target=target, new_role=action, error_message=error_message,
    ), status


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        confirm_form_identity()
        logs, receipts = retention_service.cleanup()
        audit_service.audit("limpeza")
        db.session.commit()
        flash(
            f"Limpeza concluída: {logs} registos e {receipts} comprovativos expirados eliminados."
        )
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", title="Definições")
