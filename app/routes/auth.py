from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import BadRequest

from app.services import auth_service, mfa_service

bp = Blueprint("auth", __name__)


@bp.route("/")
def index():
    return redirect(url_for("user.dashboard" if current_user.is_authenticated else "auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            auth_service.register(
                request.form.get("username", ""),
                request.form.get("password", ""),
                request.remote_addr,
            )
        except BadRequest as error:
            flash(error.description)
        else:
            flash("Registo efetuado. Autentique-se e configure a MFA.")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = auth_service.start_login(
            request.form.get("username", ""),
            request.form.get("password", ""),
            request.remote_addr,
        )
        if user:
            return redirect(url_for("auth.mfa" if user.mfa_enabled else "auth.setup_mfa"))
        flash("Credenciais inválidas ou conta indisponível.")
    return render_template("auth/login.html")


@bp.route("/setup-mfa", methods=["GET", "POST"])
def setup_mfa():
    user = auth_service.pending_user()
    if not user:
        return redirect(url_for("auth.login"))
    if user.mfa_enabled:
        return redirect(url_for("auth.mfa"))
    material = mfa_service.setup_material(user)
    if request.method == "POST":
        if auth_service.finish_mfa(
            user, request.form.get("token", ""), request.remote_addr, setup=True
        ):
            return redirect(url_for("user.dashboard"))
        flash("Código inválido ou já utilizado.")
    return render_template("auth/mfa_setup.html", **material)


@bp.route("/mfa", methods=["GET", "POST"])
def mfa():
    user = auth_service.pending_user()
    if not user:
        return redirect(url_for("auth.login"))
    if not user.mfa_enabled:
        return redirect(url_for("auth.setup_mfa"))
    if request.method == "POST":
        if auth_service.finish_mfa(user, request.form.get("token", ""), request.remote_addr):
            return redirect(url_for("user.dashboard"))
        flash("Código inválido ou já utilizado.")
    return render_template("auth/mfa_verify.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    auth_service.end_session(current_user.id)
    return redirect(url_for("auth.login"))
