"""Pseudonimização consistente; as referências continuam a ser dados pessoais."""

import hashlib
import hmac

from flask import current_app


def pseudonym(value):
    return hmac.new(
        current_app.config["AUDIT_HMAC_KEY"].encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def user_ref(uid):
    return pseudonym(f"user:{uid}")
