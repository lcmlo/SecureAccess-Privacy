r"""Executar na raiz: .\.venv\Scripts\python.exe scripts/seed_job_positions.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.services.organization_service import seed_catalog

if __name__ == "__main__":
    with create_app().app_context():
        result = seed_catalog()
        print(
            f"Departamentos: {result['departments_created']} criados, {result['departments_existing']} existentes. "
            f"Cargos: {result['positions_created']} criados, {result['positions_existing']} existentes. "
            f"Atualizados: {result['updated']}."
        )
