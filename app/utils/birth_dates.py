"""Datas civis e idades: referência UTC; aniversário de 29/02 em 01/03."""

import re
from datetime import date, datetime, timezone

from werkzeug.exceptions import BadRequest


def current_date():
    return datetime.now(timezone.utc).date()


def parse_birth_date(value, today=None):
    value = value.strip()
    if not value:
        return None
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError()
        result = date.fromisoformat(value)
    except ValueError as error:
        raise BadRequest("Introduza uma data de nascimento válida.") from error
    if result > (today if today is not None else current_date()):
        raise BadRequest("A data de nascimento não pode ser futura.")
    return result


def calculate_age(birth_date, today=None):
    if birth_date is None:
        return None
    today = today if today is not None else current_date()
    if birth_date > today:
        return None
    # Em anos não bissextos, 28/02 ainda é anterior a 29/02: só faz anos em 01/03.
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
