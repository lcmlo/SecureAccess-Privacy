"""Completa a configuração local sem substituir a chave Fernet existente."""
from pathlib import Path
import secrets
from cryptography.fernet import Fernet
from dotenv import dotenv_values

path = Path(__file__).resolve().parent.parent / '.env'
values = dotenv_values(path) if path.exists() else {}
updates = {}
if len(values.get('FLASK_SECRET_KEY') or '') < 32:
    updates['FLASK_SECRET_KEY'] = secrets.token_urlsafe(48)
if not values.get('MFA_ENC_KEY'):
    updates['MFA_ENC_KEY'] = Fernet.generate_key().decode()
if not values.get('AUDIT_HMAC_KEY'):
    updates['AUDIT_HMAC_KEY'] = secrets.token_urlsafe(48)
if updates:
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    lines = [line for line in lines if line.split('=', 1)[0].strip() not in updates]
    lines.extend(f'{key}={value}' for key, value in updates.items())
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('Configuração local pronta. Nenhum segredo foi apresentado; a chave MFA existente foi preservada.')
