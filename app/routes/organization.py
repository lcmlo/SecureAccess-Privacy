from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.exceptions import HTTPException

from app.extensions import db
from app.models import Department, JobPosition, User
from app.services import organization_service as service
from app.services.audit_service import audit
from app.utils.decorators import admin_required
from app.utils.forms import confirm_form_identity
from app.utils.pseudonymization import user_ref

bp = Blueprint("organization", __name__, url_prefix="/admin/organization")


def denied(error):
    db.session.rollback()
    audit("ORGANIZATION_CHANGE_DENIED", user_ref(current_user.id), "falha")
    db.session.commit()
    return error.description, error.code


@bp.route("/<kind>", methods=["GET", "POST"])
@bp.route("/<kind>/<int:uid>", methods=["GET", "POST"])
@admin_required
def catalog(kind, uid=None):
    if kind not in ("departments", "positions"):
        from flask import abort

        abort(404)
    error_message, status = None, 200
    if request.method == "POST":
        try:
            confirm_form_identity()
            service.save_catalog(kind, uid, request.form)
        except HTTPException as error:
            error_message, status = denied(error)
        else:
            flash("Catálogo profissional atualizado com sucesso.", "success")
            return redirect(url_for("organization.catalog", kind=kind))
    model = Department if kind == "departments" else JobPosition
    item = service.record(model, uid) if uid else None
    departments = db.session.scalars(db.select(Department).order_by(Department.name)).all()
    rows = db.session.scalars(db.select(model).order_by(model.name)).all()
    return render_template(
        "admin/organization_catalog.html",
        title="Gestão de departamentos" if kind == "departments" else "Gestão de cargos",
        kind=kind,
        item=item,
        rows=rows,
        departments=departments,
        error_message=error_message,
    ), status


@bp.route("/assign/<int:uid>", methods=["GET", "POST"])
@admin_required
def assignment(uid):
    target = service.record(User, uid)
    error_message, status = None, 200
    if request.method == "POST":
        try:
            confirm_form_identity()
            service.assign(uid, request.form)
        except HTTPException as error:
            error_message, status = denied(error)
        else:
            flash("Cargo profissional atualizado com sucesso.", "success")
            return redirect(url_for("admin.users"))
    departments = db.session.scalars(
        db.select(Department).where(Department.is_active.is_(True)).order_by(Department.name)
    ).all()
    positions = db.session.scalars(
        db.select(JobPosition)
        .join(Department)
        .where(JobPosition.is_active.is_(True), Department.is_active.is_(True))
        .order_by(JobPosition.name)
    ).all()
    return render_template(
        "admin/job_assignment.html",
        title="Atribuir/Alterar cargo",
        target=target,
        departments=departments,
        positions=positions,
        error_message=error_message,
    ), status
