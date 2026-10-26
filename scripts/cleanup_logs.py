"""Entrada agendável, sem dependência do diretório de trabalho do scheduler."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app
from app.services.retention_service import cleanup

if __name__ == "__main__":
    with create_app().app_context():
        logs, receipts = cleanup()
    print(f"Eliminados: {logs} registos e {receipts} comprovativos expirados.")
