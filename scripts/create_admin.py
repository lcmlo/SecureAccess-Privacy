"""Promove uma conta já registada e com MFA; não cria credenciais predefinidas."""

import argparse
import sys
from pathlib import Path

from werkzeug.exceptions import BadRequest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app
from app.services.user_service import promote_admin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    args = parser.parse_args()
    with create_app().app_context():
        try:
            promote_admin(args.username)
        except BadRequest as error:
            raise SystemExit(error.description) from error
    print("Perfil administrativo atribuído; autentique-se novamente.")


if __name__ == "__main__":
    main()
