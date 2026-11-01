"""Normalização comum aos serviços, índices SQLite e migrações."""

import re
import unicodedata

from werkzeug.exceptions import BadRequest

USERNAME_TAKEN = "Este nome de utilizador já está a ser utilizado."
EMAIL_TAKEN = "Este endereço de email já está associado a uma conta."


def identity_key(value):
    return unicodedata.normalize("NFC", value.strip()).casefold()


def compare_identities(left, right):
    left, right = identity_key(left), identity_key(right)
    return (left > right) - (left < right)


def normalize_email(value):
    value = value.strip()
    if value.count("@") != 1:
        raise BadRequest("Introduza um endereço de email válido.")
    local, domain = value.rsplit("@", 1)
    try:
        domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise BadRequest("Introduza um endereço de email válido.") from error
    labels = domain.split(".")
    if (
        not 1 <= len(local) <= 64
        or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+", local)
        or local.startswith(".") or local.endswith(".") or ".." in local
        or len(labels) < 2 or len(labels[-1]) < 2
        or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
        or len(local + "@" + domain) > 254
    ):
        raise BadRequest("Introduza um endereço de email válido.")
    # Política de conta: comparação insensível à caixa, sem regras de fornecedores.
    return local.lower() + "@" + domain
