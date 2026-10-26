from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import audit_service, user_service
from app.utils.pseudonymization import user_ref

bp = Blueprint("user", __name__)


@bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "admin":
        return redirect(url_for("admin.dashboard"))
    return render_template(
        "user/dashboard.html",
        title="Dashboard",
        cards=user_service.user_dashboard(current_user),
        logs=audit_service.filtered_logs(request.args, user_ref(current_user.id), 5),
    )


@bp.route("/my-data")
@login_required
def data():
    return render_template(
        "user/my_data.html", title="Os meus dados", account=current_user.public_data()
    )


@bp.route("/history")
@login_required
def history():
    return render_template(
        "user/history.html",
        title="Histórico de acessos",
        logs=audit_service.filtered_logs(request.args, user_ref(current_user.id)),
    )
