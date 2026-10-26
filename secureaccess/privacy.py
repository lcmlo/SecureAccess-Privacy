import csv
import io
import json
import sqlite3
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, request, abort, flash, Response
from flask_login import login_required, current_user
from .db import get_db, now
from .security import audit, user_ref, confirm_identity, EVENTS

bp = Blueprint('privacy', __name__)


def filtered_logs(ref=None, limit=100):
    clauses, params = [], []
    if ref:
        clauses.append('user_ref=?')
        params.append(ref)
    for field, operator in (('start', '>='), ('end', '<=')):
        value = request.args.get(field, '')
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                abort(400, description='Data inválida.')
            clauses.append(f'event_timestamp {operator} ?')
            params.append(value + (' 23:59:59' if field == 'end' else ' 00:00:00'))
    for field, allowed in (('event_type', EVENTS), ('result', ('sucesso', 'falha'))):
        value = request.args.get(field, '')
        if value:
            if value not in allowed:
                abort(400)
            clauses.append(f'{field}=?')
            params.append(value)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    try:
        page = max(1, int(request.args.get('page', '1')))
    except ValueError:
        abort(400)
    return get_db().execute('SELECT * FROM audit_logs' + where + ' ORDER BY id DESC LIMIT ? OFFSET ?', params + [limit, (page - 1) * limit]).fetchall()


@bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    ref = user_ref(current_user.id)
    last = get_db().execute("SELECT event_timestamp FROM audit_logs WHERE user_ref=? AND event_type='login' AND result='sucesso' ORDER BY id DESC LIMIT 1", (ref,)).fetchone()
    cards = [('Estado da MFA', 'Ativa' if current_user.mfa_enabled else 'Inativa', 'Proteção da conta por dois fatores.', 'privacy.data'),
             ('Último acesso', last['event_timestamp'] + ' UTC' if last else 'Sem registo conservado', 'Última autenticação bem-sucedida conservada.', 'privacy.history'),
             ('Privacidade', 'Dados minimizados', 'Registos pseudonimizados e retenção limitada.', 'privacy.center'),
             ('Os meus dados', 'Consultar e exportar', 'Aceda às informações associadas à sua conta.', 'privacy.data')]
    return render_template('dashboard.html', title='Dashboard', cards=cards, logs=filtered_logs(ref, 5))


@bp.route('/my-data')
@login_required
def data():
    row = get_db().execute('SELECT id,username,role,mfa_enabled,created_at,active FROM users WHERE id=?', (current_user.id,)).fetchone()
    return render_template('data.html', title='Os meus dados', account=row)


@bp.route('/history')
@login_required
def history():
    return render_template('logs.html', title='Histórico de acessos', logs=filtered_logs(user_ref(current_user.id)), administrative=False)


@bp.route('/privacy')
@login_required
def center():
    return render_template('privacy.html', title='Centro de Privacidade')


@bp.route('/export', methods=['GET', 'POST'])
@login_required
def export():
    if request.method == 'POST':
        categories = request.form.getlist('categories')
        fmt = request.form.get('format')
        if not categories or not set(categories) <= {'account', 'history', 'requests'} or fmt not in ('json', 'csv'):
            abort(400)
        confirm_identity()
        db = get_db()
        payload = {}
        if 'account' in categories:
            payload['account'] = dict(db.execute('SELECT id,username,role,mfa_enabled,created_at,active FROM users WHERE id=?', (current_user.id,)).fetchone())
        if 'history' in categories:
            payload['history'] = [dict(r) for r in db.execute('SELECT event_type,event_timestamp,result FROM audit_logs WHERE user_ref=? ORDER BY id', (user_ref(current_user.id),))]
        if 'requests' in categories:
            payload['requests'] = [dict(r) for r in db.execute('SELECT id,requested_at,status,completed_at FROM deletion_requests WHERE user_id=? ORDER BY id', (current_user.id,))]
        audit('exportacao')
        db.commit()
        if fmt == 'json':
            content = json.dumps(payload, ensure_ascii=False, indent=2)
            mime = 'application/json'
        else:
            buffer = io.StringIO(newline='')
            writer = csv.writer(buffer)
            writer.writerow(['categoria', 'registo', 'campo', 'valor'])
            for category, values in payload.items():
                for index, record in enumerate(values if isinstance(values, list) else [values], 1):
                    for key, value in record.items():
                        text = '' if value is None else str(value)
                        if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
                            text = "'" + text
                        writer.writerow([category, index, key, text])
            content, mime = '\ufeff' + buffer.getvalue(), 'text/csv'
        return Response(content, mimetype=mime, headers={'Content-Disposition': f'attachment; filename="secureaccess-dados.{fmt}"'})
    return render_template('export.html', title='Exportação de dados')


@bp.route('/deletion', methods=['GET', 'POST'])
@login_required
def deletion():
    if request.method == 'POST':
        if request.form.get('confirmation') != 'ELIMINAR':
            abort(400, description='Escreva ELIMINAR para confirmar.')
        confirm_identity()
        db = get_db()
        try:
            cursor = db.execute('INSERT INTO deletion_requests(user_id,requested_at) VALUES(?,?)', (current_user.id, now()))
            db.execute('INSERT INTO deletion_history(request_id,status,changed_at) VALUES(?,?,?)', (cursor.lastrowid, 'pendente', now()))
            audit('pedido_eliminacao')
            db.commit()
            flash('Pedido registado. Aguarda análise administrativa.')
        except sqlite3.IntegrityError:
            db.rollback()
            flash('Já existe um pedido de eliminação em aberto.')
        return redirect(url_for('privacy.deletion'))
    rows = get_db().execute('SELECT * FROM deletion_requests WHERE user_id=? ORDER BY id DESC', (current_user.id,)).fetchall()
    return render_template('deletion.html', title='Pedido de eliminação', requests=rows)
