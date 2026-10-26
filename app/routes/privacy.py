from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.services import privacy_service
from app.utils.forms import confirm_form_identity

bp = Blueprint("privacy", __name__)


@bp.route("/privacy")
@login_required
def center():
    return render_template("user/privacy_center.html", title="Centro de Privacidade")


@bp.route("/export", methods=["GET", "POST"])
@login_required
def export():
    if request.method == "POST":
        categories, fmt = request.form.getlist("categories"), request.form.get("format")
        if (
            not categories
            or not set(categories) <= {"account", "history", "requests"}
            or fmt not in ("json", "csv")
        ):
            abort(400)
        confirm_form_identity()
        content, mime = privacy_service.export_data(current_user.id, categories, fmt)
        return Response(
            content,
            mimetype=mime,
            headers={"Content-Disposition": f'attachment; filename="secureaccess-dados.{fmt}"'},
        )
    return render_template("user/export_data.html", title="Exportação de dados")


@bp.route("/deletion", methods=["GET", "POST"])
@login_required
def deletion():
    if request.method == "POST":
        if request.form.get("confirmation") != "ELIMINAR":
            abort(400, description="Escreva ELIMINAR para confirmar.")
        confirm_form_identity()
        if privacy_service.create_deletion_request(current_user.id):
            flash("Pedido registado. Aguarda análise administrativa.")
        else:
            flash("Já existe um pedido de eliminação em aberto.")
        return redirect(url_for("privacy.deletion"))
    return render_template(
        "user/deletion_request.html",
        title="Pedido de eliminação",
        requests=privacy_service.own_requests(current_user.id),
    )
