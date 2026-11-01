import io

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import BadRequest, Forbidden

from app.extensions import db
from app.services import audit_service, profile_service, user_service
from app.services.profile_photo import read_photo
from app.utils.birth_dates import calculate_age, current_date
from app.utils.forms import confirm_form_identity
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


@bp.route("/my-data/edit", methods=["GET", "POST"])
@login_required
def edit_data():
    values = current_user.public_data()
    error_message = None
    status = 200
    if request.method == "POST":
        values.update({
            "username": request.form.get("username", ""),
            "full_name": request.form.get("full_name", ""),
            "email": request.form.get("email", current_user.email or ""),
            **{field: request.form.get(field, "") for field in profile_service.PERSONAL_FIELDS},
        })
        values["age"] = None
        try:
            profile_service.validate_profile(values["username"], values["full_name"])
            details = profile_service.validate_details(values)
            values["age"] = calculate_age(details["birth_date"])
            photo = read_photo(request.files.get("photo"))
            confirm_form_identity()
            profile_service.update_profile(
                values["username"], values["full_name"], email=values["email"],
                details=values, photo=photo, remove_photo=request.form.get("remove_photo") == "1",
            )
        except (BadRequest, Forbidden) as error:
            db.session.rollback()
            audit_service.audit("dados_pessoais_alterados", user_ref(current_user.id), "falha")
            db.session.commit()
            error_message, status = error.description, error.code
        else:
            flash("Dados pessoais atualizados com sucesso.", "success")
            return redirect(url_for("user.data"))
    return render_template(
        "user/edit_data.html", title="Editar dados", values=values, error_message=error_message,
        today=current_date().isoformat(),
    ), status


@bp.route("/my-data/photo")
@login_required
def profile_photo():
    profile = current_user.profile
    if not profile or not profile.photo:
        abort(404)
    return send_file(io.BytesIO(profile.photo), mimetype="image/jpeg", download_name="perfil.jpg", max_age=0)


@bp.route("/history")
@login_required
def history():
    return render_template(
        "user/history.html",
        title="Histórico de acessos",
        logs=audit_service.filtered_logs(request.args, user_ref(current_user.id)),
    )
