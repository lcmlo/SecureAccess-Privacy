import os, sqlite3, base64, io
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import pyotp, qrcode
from cryptography.fernet import Fernet
from dotenv import load_dotenv
load_dotenv()

ENC_KEY = os.environ.get("MFA_ENC_KEY")
if not ENC_KEY:
    raise RuntimeError("⚠️ Define MFA_ENC_KEY no ficheiro .env antes de correr a app.")
fernet = Fernet(ENC_KEY.encode())

DB_PATH = os.environ.get("MFA_DB_PATH", "mfa.db")
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "change-me")
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

login_manager = LoginManager(app)
login_manager.login_view = 'login'

def encrypt_secret(secret):
    return fernet.encrypt(secret.encode()).decode()

def decrypt_secret(ciphertext):
    return fernet.decrypt(ciphertext.encode()).decode()

# Inicializa a base de dados no arranque da aplicação
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        totp_secret TEXT,
        mfa_enabled INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    conn.commit()
    conn.close()

# Criar a BD ao iniciar
with app.app_context():
    init_db()

class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.username = row['username']
        self.password_hash = row['password_hash']
        self.totp_secret = row['totp_secret']
        self.mfa_enabled = row['mfa_enabled']

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return User(row) if row else None

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Username e password são obrigatórios.')
            return render_template('register.html')
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                         (username, generate_password_hash(password)))
            conn.commit()
            flash('Registo efetuado com sucesso. Faz login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Esse username já existe.')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row['password_hash'], password):
            session['pending_user_id'] = row['id']
            session['pending_username'] = row['username']
            if row['mfa_enabled']:
                return redirect(url_for('mfa'))
            else:
                return redirect(url_for('setup_mfa'))
        else:
            flash('Credenciais inválidas.')
    return render_template('login.html')

def get_pending_user():
    uid = session.get('pending_user_id')
    if not uid:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return row

@app.route('/setup-mfa', methods=['GET','POST'])
def setup_mfa():
    row = get_pending_user()
    if not row:
        return redirect(url_for('login'))

    # Atribuir segredo TOTP, se ainda não existir
    if not row['totp_secret']:
        secret = pyotp.random_base32()
        encrypted = encrypt_secret(secret)
        conn = get_db()
        conn.execute("UPDATE users SET totp_secret=? WHERE id=?", (encrypted, row['id']))
        conn.commit()
        conn.close()
        row = get_pending_user()

    secret = decrypt_secret(row['totp_secret'])

    username = row['username']
    uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="SRSI-MFA-Demo")

    # QR Code em memória (Base64)
    qr_img = qrcode.make(uri)
    buf = io.BytesIO()
    qr_img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    if request.method == 'POST':
        token = request.form['token'].strip()
        totp = pyotp.TOTP(secret)
        if totp.verify(token):
            conn = get_db()
            conn.execute("UPDATE users SET mfa_enabled=1 WHERE id=?", (row['id'],))
            conn.commit()
            conn.close()

            user_obj = User(row)
            login_user(user_obj)
            session.pop('pending_user_id', None)
            session.pop('pending_username', None)
            flash('✅ MFA ativado com sucesso.')
            return redirect(url_for('dashboard'))
        else:
            flash('❌ Código inválido. Tenta novamente.')

    return render_template('setup_mfa.html', qr_b64=qr_b64, secret=secret, uri=uri, username=username)

@app.route('/mfa', methods=['GET','POST'])
def mfa():
    row = get_pending_user()
    if not row:
        return redirect(url_for('login'))
    secret = decrypt_secret(row['totp_secret'])
    if not secret:
        return redirect(url_for('setup_mfa'))

    if request.method == 'POST':
        token = request.form['token'].strip()
        totp = pyotp.TOTP(secret)
        if totp.verify(token):
            user_obj = User(row)
            login_user(user_obj)
            session.pop('pending_user_id', None)
            session.pop('pending_username', None)
            flash('🔐 Autenticação concluída.')
            return redirect(url_for('dashboard'))
        else:
            flash('❌ Código inválido.')
    return render_template('mfa.html', username=row['username'])

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html',
                           username=current_user.username,
                           mfa_enabled=bool(current_user.mfa_enabled))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sessão terminada.')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)


