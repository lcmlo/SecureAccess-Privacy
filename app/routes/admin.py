from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
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
    confirm_form_identity()
    user_service.update_user(current_user.id, uid, action)
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
    return render_template("admin/permissions.html", title="Perfis e permissões")


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
