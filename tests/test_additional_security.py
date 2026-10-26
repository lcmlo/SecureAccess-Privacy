from app.extensions import db

from .conftest import signin
from .db_helpers import get_db


def test_no_sensitive_fields_in_any_user_page(app, client):
    uid, secret = signin(client, app)
    for path in [
        "/dashboard",
        "/my-data",
        "/history",
        "/privacy",
        "/export",
        "/deletion",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert secret.encode() not in response.data
        assert b"password_hash" not in response.data and b"/admin/" not in response.data


def test_sql_injection_and_escaping(app, client):
    aid, _ = signin(client, app, "administrador", "admin")
    assert client.get("/admin/users?q=%27%20OR%201=1--").status_code == 200
    assert "Não foram encontradas".encode() in client.get("/admin/users?q=%27%20OR%201=1--").data
    with app.app_context():
        get_db().execute(
            "INSERT INTO users(username,password_hash) VALUES(?,?)",
            ("<script>alert(1)</script>", "legacy"),
        )
        get_db().commit()
        db.session.commit()
    response = client.get("/admin/users")
    assert b"<script>alert(1)</script>" not in response.data
    assert b"&lt;script&gt;" in response.data
