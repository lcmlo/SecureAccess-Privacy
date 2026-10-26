"""Adapta a confirmação de um formulário HTTP à assinatura do serviço."""

from flask import request
from flask_login import current_user

from app.services.auth_service import confirm_identity


def confirm_form_identity():
    confirm_identity(
        current_user.id,
        request.form.get("password", ""),
        request.form.get("token", ""),
        request.remote_addr,
    )
