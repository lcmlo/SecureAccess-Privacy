import csv
import io
import json
import pytest
from .conftest import signin, seed, post, confirmation
from secureaccess.db import get_db, cleanup
from secureaccess.security import audit, user_ref


@pytest.mark.parametrize('path', ['/admin/', '/admin/users', '/admin/logs', '/admin/deletions', '/admin/permissions', '/admin/settings'])
def test_user_cannot_admin(app, client, path):
    signin(client, app)
    assert client.get(path).status_code == 403
    assert post(client, '/admin/users/1', {'action': 'admin'}).status_code == 403


def test_own_data_and_filters(app, client):
    uid, _ = signin(client, app)
    other, _ = seed(app, 'outra')
    with app.app_context():
        audit('exportacao', user_ref(other))
        audit('mfa_falha', user_ref(uid), 'falha')
        get_db().commit()
    response = client.get('/my-data?user_id=' + str(other))
    assert b'alice' in response.data and b'outra' not in response.data
    response = client.get('/history?event_type=exportacao')
    assert 'Não existem registos'.encode() in response.data
    response = client.get('/history?event_type=mfa_falha&result=falha')
    assert 'Falha na MFA'.encode() in response.data
    assert client.get('/history?start=invalid').status_code == 400
    assert client.get('/history?result=anything').status_code == 400
    assert client.get('/history?start=2000-01-01&end=2000-01-02').status_code == 200
    assert b'/admin/' not in client.get('/dashboard').data


@pytest.mark.parametrize('fmt', ['json', 'csv'])
def test_export_safety_and_ownership(app, client, fmt):
    uid, secret = signin(client, app)
    seed(app, 'outra')
    data = confirmation(app, uid, secret)
    data.update({'categories': ['account', 'history', 'requests'], 'format': fmt, 'user_id': 999})
    response = post(client, '/export', data)
    assert response.status_code == 200 and 'attachment' in response.headers['Content-Disposition']
    body = response.get_data(as_text=True)
    for forbidden in ['password_hash', 'totp_secret', 'session_version', 'last_totp_step', secret, 'outra']:
        assert forbidden not in body
    if fmt == 'json':
        assert json.loads(body)['account']['id'] == uid
    else:
        rows = list(csv.reader(io.StringIO(body.lstrip('\ufeff'))))
        assert rows[0] == ['categoria', 'registo', 'campo', 'valor']
        assert any(r[-1] == 'alice' for r in rows)
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM audit_logs WHERE user_ref=? AND event_type='exportacao'", (user_ref(uid),)).fetchone()[0] == 1


def test_sensitive_confirmation_and_export_categories(app, client):
    uid, secret = signin(client, app)
    assert post(client, '/export', {'categories': ['account'], 'format': 'json', 'password': 'errada', 'token': '000000'}).status_code == 403
    assert post(client, '/export', {'categories': ['secrets'], 'format': 'json'}).status_code == 400
    assert post(client, '/deletion', {'confirmation': 'nao'}).status_code == 400


def test_deletion_workflow(app, client):
    uid, secret = signin(client, app)
    data = confirmation(app, uid, secret)
    data['confirmation'] = 'ELIMINAR'
    assert post(client, '/deletion', data).status_code == 302
    with app.app_context():
        row = get_db().execute('SELECT * FROM deletion_requests').fetchone()
        rid = row['id']
        assert row['user_id'] == uid and row['status'] == 'pendente'
        assert get_db().execute("SELECT COUNT(*) FROM audit_logs WHERE event_type='pedido_eliminacao'").fetchone()[0] == 1
    data = confirmation(app, uid, secret)
    assert post(client, '/deletion', {**data, 'confirmation': 'ELIMINAR'}).status_code == 302
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM deletion_requests').fetchone()[0] == 1
    admin_client = app.test_client()
    aid, asecret = signin(admin_client, app, 'administrador', 'admin')
    path = f'/admin/deletions/{rid}'
    assert post(admin_client, path, {**confirmation(app, aid, asecret), 'action': 'complete'}).status_code == 409
    assert post(admin_client, path, {**confirmation(app, aid, asecret), 'action': 'process'}).status_code == 302
    assert post(admin_client, path, {**confirmation(app, aid, asecret), 'action': 'complete'}).status_code == 302
    with app.app_context():
        db = get_db()
        assert db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone() is None
        assert db.execute('SELECT * FROM audit_logs WHERE user_ref=?', (user_ref(uid),)).fetchone() is None
        row = db.execute('SELECT * FROM deletion_requests').fetchone()
        assert row['status'] == 'concluído' and row['user_id'] is None and row['completed_at']
        assert db.execute('SELECT COUNT(*) FROM deletion_history WHERE request_id=?', (rid,)).fetchone()[0] == 3
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert client.get('/my-data').status_code == 302


def test_other_users_cannot_see_requests(app, client):
    uid, secret = signin(client, app)
    post(client, '/deletion', {**confirmation(app, uid, secret), 'confirmation': 'ELIMINAR'})
    second = app.test_client()
    signin(second, app, 'bob')
    assert 'Ainda não apresentou'.encode() in second.get('/deletion?user_id=1').data
    assert second.get('/export/1').status_code == 404


def test_retention(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO audit_logs(user_ref,event_type,event_timestamp,result) VALUES('ref','login','2000-01-01 00:00:00','sucesso')")
        audit('login', 'recent-ref')
        rid = db.execute("INSERT INTO deletion_requests(requested_at,status,completed_at) VALUES('2000-01-01','concluído','2000-01-02')").lastrowid
        db.execute("INSERT INTO deletion_history(request_id,status,changed_at) VALUES(?,'concluído','2000-01-02')", (rid,))
        db.execute("INSERT INTO deletion_requests(requested_at,status) VALUES('2000-01-01','pendente')")
        db.commit()
        assert cleanup() == (1, 1)
        assert db.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM deletion_history').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM deletion_requests').fetchone()[0] == 1
