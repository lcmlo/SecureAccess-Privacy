from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, abort, redirect, url_for, flash
from flask_login import current_user
from .db import get_db, now, cleanup
from .security import admin_required, audit, user_ref, confirm_identity, pseudonym
from .privacy import filtered_logs

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/')
@admin_required
def dashboard():
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    cards = [
        ('Utilizadores ativos', db.execute('SELECT COUNT(*) FROM users WHERE active=1').fetchone()[0], 'Contas com acesso autorizado.', 'admin.users'),
        ('Falhas de autenticação', db.execute("SELECT COUNT(*) FROM audit_logs WHERE result='falha' AND event_type IN ('login','mfa_falha') AND event_timestamp>=?", (since,)).fetchone()[0], 'Nas últimas 24 horas.', 'admin.logs'),
        ('Pedidos pendentes', db.execute("SELECT COUNT(*) FROM deletion_requests WHERE status='pendente'").fetchone()[0], 'A aguardar processamento.', 'admin.deletions'),
        ('MFA ativa', db.execute('SELECT COUNT(*) FROM users WHERE active=1 AND mfa_enabled=1').fetchone()[0], 'Contas ativas com MFA configurada.', 'admin.users')]
    return render_template('dashboard.html', title='Dashboard', cards=cards, logs=filtered_logs(limit=5), administrative=True)


@bp.route('/users')
@admin_required
def users():
    role = request.args.get('role', '')
    if role not in ('', 'user', 'admin'):
        abort(400)
    query = request.args.get('q', '')[:64]
    rows = get_db().execute("SELECT id,username,role,mfa_enabled,active FROM users WHERE instr(lower(username),lower(?))>0 AND (?='' OR role=?) ORDER BY id LIMIT 200", (query, role, role)).fetchall()
    return render_template('users.html', title='Utilizadores', users=rows)


@bp.route('/users/<int:uid>', methods=['POST'])
@admin_required
def update_user(uid):
    action = request.form.get('action')
    if action not in ('activate', 'deactivate', 'user', 'admin') or uid == current_user.id:
        abort(403)
    confirm_identity()
    db = get_db()
    db.execute('BEGIN IMMEDIATE')
    target = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not target:
        abort(404)
    if action == 'admin' and (not target['mfa_enabled'] or not target['active']):
        abort(409, description='A conta deve estar ativa e ter MFA configurada.')
    if target['role'] == 'admin' and target['active'] and action in ('deactivate', 'user'):
        if db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0] <= 1:
            abort(409, description='Não pode remover o último administrador ativo.')
    if action in ('user', 'admin'):
        db.execute('UPDATE users SET role=?,session_version=session_version+1 WHERE id=?', (action, uid))
        event = 'perfil_alterado'
    else:
        db.execute('UPDATE users SET active=?,session_version=session_version+1 WHERE id=?', (int(action == 'activate'), uid))
        event = 'conta_alterada'
    # Dois eventos: autoria administrativa e referência pseudonimizada da conta afetada.
    audit(event)
    audit(event, user_ref(uid))
    db.commit()
    flash('Conta atualizada. Sessões anteriores revogadas.')
    return redirect(url_for('admin.users'))


@bp.route('/logs')
@admin_required
def logs():
    return render_template('logs.html', title='Logs de autenticação', logs=filtered_logs(), administrative=True)


@bp.route('/deletions')
@admin_required
def deletions():
    rows = get_db().execute('SELECT * FROM deletion_requests ORDER BY id DESC LIMIT 200').fetchall()
    histories = {r['id']: get_db().execute('SELECT status,changed_at FROM deletion_history WHERE request_id=? ORDER BY id', (r['id'],)).fetchall() for r in rows}
    return render_template('admin_deletions.html', title='Pedidos de eliminação', requests=rows, histories=histories, user_ref=user_ref)


@bp.route('/deletions/<int:rid>', methods=['POST'])
@admin_required
def process_deletion(rid):
    action = request.form.get('action')
    if action not in ('process', 'complete'):
        abort(400)
    confirm_identity()
    db = get_db()
    db.execute('BEGIN IMMEDIATE')
    row = db.execute('SELECT * FROM deletion_requests WHERE id=?', (rid,)).fetchone()
    if not row:
        abort(404)
    if row['user_id'] == current_user.id:
        abort(403, description='Outro administrador deve tratar o seu pedido.')
    if action == 'process' and row['status'] == 'pendente':
        status, event = 'em processamento', 'eliminacao_processamento'
        db.execute('UPDATE deletion_requests SET status=? WHERE id=?', (status, rid))
        audit(event, user_ref(row['user_id']))
    elif action == 'complete' and row['status'] == 'em processamento':
        target = db.execute('SELECT * FROM users WHERE id=?', (row['user_id'],)).fetchone()
        if target and target['role'] == 'admin' and target['active']:
            if db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0] <= 1:
                abort(409)
        status, event = 'concluído', 'eliminacao_concluida'
        db.execute('DELETE FROM audit_logs WHERE user_ref=?', (user_ref(row['user_id']),))
        if target:
            for identity in (f"login:identity:{target['username'].casefold()}",
                             f"mfa:identity:{target['id']}", f"confirm:identity:{target['id']}"):
                db.execute('DELETE FROM auth_attempts WHERE bucket=?', (pseudonym(identity),))
        db.execute('UPDATE deletion_requests SET status=?,completed_at=? WHERE id=?', (status, now(), rid))
        db.execute('DELETE FROM users WHERE id=?', (row['user_id'],))
        # FK SET NULL desvincula o comprovativo; não se conserva a referência da conta.
    else:
        abort(409, description='Transição de estado inválida.')
    db.execute('INSERT INTO deletion_history(request_id,status,changed_at) VALUES(?,?,?)', (rid, status, now()))
    audit(event)
    db.commit()
    flash('Pedido atualizado. A conclusão executa a eliminação na mesma transação.')
    return redirect(url_for('admin.deletions'))


@bp.route('/permissions')
@admin_required
def permissions():
    return render_template('permissions.html', title='Perfis e permissões')


@bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        confirm_identity()
        logs, receipts = cleanup()
        audit('limpeza')
        get_db().commit()
        flash(f'Limpeza concluída: {logs} registos e {receipts} comprovativos expirados eliminados.')
        return redirect(url_for('admin.settings'))
    return render_template('settings.html', title='Definições')
