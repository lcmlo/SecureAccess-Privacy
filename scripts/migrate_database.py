"""Copia a base legada e aplica Alembic; --dry-run nunca altera a origem."""

import argparse
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def copy_database(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(source)) as original,
        closing(sqlite3.connect(target)) as destination,
    ):
        original.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Falhou a verificação de integridade da cópia.")


def upgrade_database(path):
    from flask_migrate import upgrade

    from app import create_app
    from app.extensions import db

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///" + path.resolve().as_posix()})
    with app.app_context():
        try:
            upgrade()
        finally:
            db.session.remove()
            db.engine.dispose()
    with closing(sqlite3.connect(path)) as connection:
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foram detetadas relações inválidas.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    target = ROOT / "instance" / "secureaccess.db"
    configured = os.getenv("MFA_DB_PATH") or dotenv_values(ROOT / ".env").get("MFA_DB_PATH")
    source = args.source or (Path(configured) if configured else ROOT / "mfa.db")
    if not source.is_absolute():
        source = ROOT / source
    if args.source and not source.exists():
        raise SystemExit("A base indicada em --source não existe; nenhuma alteração foi aplicada.")
    if not args.source and not source.exists():
        if target.exists():
            source = target
        elif (ROOT / "mfa.db").exists():
            source = ROOT / "mfa.db"
    if args.dry_run:
        with tempfile.TemporaryDirectory() as directory:
            trial = Path(directory) / "trial.db"
            if source.exists():
                copy_database(source, trial)
            upgrade_database(trial)
        print("Simulação Alembic concluída numa cópia temporária; origem preservada.")
        return
    if source.exists() and source.resolve() != target.resolve():
        if target.exists():
            raise SystemExit(
                "O destino já existe. Não será substituído; selecione explicitamente a base a conservar."
            )
        copy_database(source, target)
    upgrade_database(target)
    set_key(str(ROOT / ".env"), "MFA_DB_PATH", "instance/secureaccess.db")
    print(
        "Base em instance/secureaccess.db migrada. Configuração atualizada; origem e backups preservados."
    )


if __name__ == "__main__":
    main()
