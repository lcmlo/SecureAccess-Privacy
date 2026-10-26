"""Controlos HTTP comuns; CSRF é validado pela extensão Flask-WTF."""

import time

from flask import current_app, render_template, request, session
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import default_exceptions

from app.extensions import db
from app.services.audit_service import EVENTS
from app.services.retention_service import cleanup


def init_app(app):
    @app.before_request
    def protect():
        if request.endpoint != "static":
            cleanup()
        if (
            current_user.is_authenticated
            and time.time() - session.get("authenticated_at", 0) >= 1800
        ):
            logout_user()
            session.clear()

    @app.context_processor
    def shared():
        return dict(
            events=EVENTS,
            retention=current_app.config["LOG_RETENTION_DAYS"],
            receipts_retention=current_app.config["RECEIPT_RETENTION_DAYS"],
        )

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def handle_error(error):
        db.session.rollback()
        message = "O recurso não está disponível ou não tem permissão para esta operação."
        if isinstance(error, CSRFError):
            message = "Formulário expirado. Recarregue a página."
        elif (
            error.code in (400, 409, 429)
            and error.description != default_exceptions[error.code].description
        ):
            message = error.description
        elif error.code == 405:
            message = "Este método não é permitido. Utilize o formulário da aplicação."
        elif error.code == 413:
            message = "O pedido excede o tamanho permitido."
        template = (
            f"errors/{error.code}.html" if error.code in (403, 404, 500) else "errors/generic.html"
        )
        return render_template(template, error=error, error_message=message), error.code

    for code in (400, 403, 404, 405, 409, 413, 429, 500):
        app.register_error_handler(code, handle_error)
