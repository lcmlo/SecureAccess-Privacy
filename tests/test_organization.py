import json
from types import SimpleNamespace
from unittest.mock import patch

import pyotp
import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AuditLog, Department, JobPosition, User, UserProfile
from app.services.organization_service import seed_catalog
from tests.conftest import confirmation, post, seed, signin


def catalog(app):
    with app.app_context():
        seed_catalog()
        positions = db.session.scalars(db.select(JobPosition).order_by(JobPosition.id)).all()
        return [(p.id, p.department_id) for p in positions]


def send(client, app, actor, secret, path, data):
    identity = confirmation(app, actor, secret)
    identity["token"] = pyotp.TOTP(secret).at(1800000000)
    with patch("app.services.mfa_service.time", SimpleNamespace(time=lambda: 1800000000)):
        return post(client, path, {**identity, **data})


def test_seed_idempotent_and_preserves_existing(app):
    with app.app_context():
        first = seed_catalog()
        assert first["departments_created"] == 6
        assert first["positions_created"] == 21
        p = db.session.scalar(db.select(JobPosition))
        p.is_active = False
        db.session.add(Department(name="Extra"))
        db.session.commit()
        second = seed_catalog()
        assert second["departments_existing"] == 6
        assert second["positions_existing"] == 21
        assert second["positions_created"] == 0
        assert not db.session.get(JobPosition, p.id).is_active
        assert db.session.scalar(db.select(db.func.count()).select_from(Department)) == 7


@pytest.mark.parametrize("position", [False, True])
def test_database_uniqueness(app, position):
    catalog(app)
    with app.app_context():
        if position:
            first = db.session.scalar(db.select(JobPosition))
            item = JobPosition(
                name="  " + first.name.upper().replace(" ", "   ") + " ",
                department_id=first.department_id,
            )
        else:
            first = db.session.scalar(db.select(Department))
            item = Department(name="  " + first.name.upper().replace(" ", "   ") + " ")
        db.session.add(item)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize("target_role", ["user", "admin"])
def test_assignment_change_removal_export_and_audit(client, app, target_role):
    actor, secret = signin(client, app, role="admin")
    target, _ = seed(app, "colaborador", target_role)
    positions = catalog(app)
    path = f"/admin/organization/assign/{target}"
    for index in (0, 1):
        pid, did = positions[index]
        assert (
            send(
                client, app, actor, secret, path, {"job_position_id": pid, "department_id": did}
            ).status_code
            == 302
        )
        with app.app_context():
            user = db.session.get(User, target)
            assert user.role == target_role
            assert user.profile.job_position_id == pid
    with app.app_context():
        from app.services.privacy_service import export_data

        data = json.loads(export_data(target, ["account"], "json")[0])["account"]
        assert data["department"] and data["job_position"]
        assert "password_hash" not in data
        assert set(db.session.scalars(db.select(AuditLog.event_type))) >= {
            "JOB_POSITION_ASSIGNED",
            "JOB_POSITION_CHANGED",
        }
    assert send(client, app, actor, secret, path, {"action": "remove"}).status_code == 302
    with app.app_context():
        assert db.session.get(User, target).profile.job_position_id is None
        assert db.session.scalar(
            db.select(AuditLog).where(AuditLog.event_type == "JOB_POSITION_REMOVED")
        )


@pytest.mark.parametrize(
    "invalid", ["mismatch", "position_inactive", "department_inactive", "missing"]
)
def test_invalid_assignments(client, app, invalid):
    actor, secret = signin(client, app, role="admin")
    target, _ = seed(app, "destino")
    positions = catalog(app)
    pid, did = positions[0]
    if invalid == "mismatch":
        did = positions[-1][1]
    elif invalid == "missing":
        pid = 999999
    else:
        with app.app_context():
            item = (
                db.session.get(JobPosition, pid)
                if invalid == "position_inactive"
                else db.session.get(Department, did)
            )
            item.is_active = False
            db.session.commit()
    response = send(
        client,
        app,
        actor,
        secret,
        f"/admin/organization/assign/{target}",
        {"job_position_id": pid, "department_id": did},
    )
    assert response.status_code in (400, 404, 409)
    with app.app_context():
        assert not db.session.get(User, target).profile


@pytest.mark.parametrize("kind", ["departments", "positions"])
def test_catalog_crud_and_audit(client, app, kind):
    actor, secret = signin(client, app, role="admin")
    positions = catalog(app)
    data = {"name": "Novo registo", "description": "Descrição", "department_id": positions[0][1]}
    path = "/admin/organization/" + kind
    assert send(client, app, actor, secret, path, data).status_code == 302
    model = Department if kind == "departments" else JobPosition
    with app.app_context():
        uid = db.session.scalar(db.select(model.id).where(model.name == data["name"]))
    for action in ("deactivate", "reactivate"):
        assert (
            send(client, app, actor, secret, f"{path}/{uid}", {"action": action}).status_code == 302
        )
    assert (
        send(
            client, app, actor, secret, f"{path}/{uid}", {**data, "name": "Nome alterado"}
        ).status_code
        == 302
    )
    with app.app_context():
        assert db.session.get(model, uid).name == "Nome alterado"
        prefix = "DEPARTMENT" if kind == "departments" else "JOB_POSITION"
        assert set(db.session.scalars(db.select(AuditLog.event_type))) >= {
            prefix + suffix for suffix in ("_CREATED", "_UPDATED", "_DEACTIVATED", "_REACTIVATED")
        }


def test_move_assigned_requires_confirmation(client, app):
    actor, secret = signin(client, app, role="admin")
    pid, did = catalog(app)[0]
    send(
        client,
        app,
        actor,
        secret,
        f"/admin/organization/assign/{actor}",
        {"job_position_id": pid, "department_id": did},
    )
    with app.app_context():
        other = Department(name="Outro departamento")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    data = {"name": "Novo nome", "department_id": other_id}
    path = f"/admin/organization/positions/{pid}"
    assert send(client, app, actor, secret, path, data).status_code == 409
    assert send(client, app, actor, secret, path, {**data, "confirm_move": "1"}).status_code == 302
    with app.app_context():
        assert db.session.get(User, actor).profile.job_position.department_id == other_id


@pytest.mark.parametrize(
    "path",
    [
        "/admin/organization/departments",
        "/admin/organization/positions",
        "/admin/organization/assign/1",
    ],
)
def test_user_denied_get_post(client, app, path):
    signin(client, app)
    assert client.get(path).status_code == 403
    assert post(client, path, {"name": "Indevido"}).status_code == 403


def test_profile_tampering_and_persistence(client, app):
    actor, secret = signin(client, app, role="admin")
    pid, did = catalog(app)[0]
    assert (
        send(
            client,
            app,
            actor,
            secret,
            f"/admin/organization/assign/{actor}",
            {"job_position_id": pid, "department_id": did},
        ).status_code
        == 302
    )
    response = send(
        client,
        app,
        actor,
        secret,
        "/my-data/edit",
        {
            "username": "alice",
            "full_name": "",
            "job_position_id": "",
            "department_id": "",
            "role": "user",
        },
    )
    assert response.status_code == 302
    html = client.get("/my-data").get_data(as_text=True)
    assert "Direção" in html and "Diretor-Geral (CEO)" in html
    assert "readonly" in client.get("/my-data/edit").get_data(as_text=True)
    with app.app_context():
        account = db.session.get(User, actor)
        assert account.profile.job_position_id == pid and account.role == "admin"
    assert post(client, "/logout").status_code == 302
    import pyotp

    from tests.conftest import PASSWORD

    confirmation(app, actor, secret)
    assert post(client, "/login", {"username": "alice", "password": PASSWORD}).status_code == 302
    assert post(client, "/mfa", {"token": pyotp.TOTP(secret).now()}).status_code == 302
    assert "Diretor-Geral (CEO)" in client.get("/my-data").get_data(as_text=True)


def test_csrf_reauthentication_and_filters(client, app):
    actor, secret = signin(client, app, role="admin")
    pid, did = catalog(app)[0]
    path = f"/admin/organization/assign/{actor}"
    assert client.post(path, data={"job_position_id": pid, "department_id": did}).status_code == 400
    response = post(
        client,
        path,
        {"job_position_id": pid, "department_id": did},
    )

    assert response.status_code == 400
    assert "Não foi possível confirmar a identidade" in response.get_data(as_text=True)
    assert (
        send(
            client, app, actor, secret, path, {"job_position_id": pid, "department_id": did}
        ).status_code
        == 302
    )
    assert (
        client.get(
            f"/admin/users?department_id={did}&job_position_id={pid}&role=admin&active=1&q=alice"
        ).status_code
        == 200
    )
    assert client.get("/admin/users?department_id=invalid").status_code == 400


def test_profile_deletion_preserves_catalog(app):
    uid, _ = seed(app)
    pid, _ = catalog(app)[0]
    with app.app_context():
        user = db.session.get(User, uid)
        user.profile = UserProfile(job_position_id=pid, job_title="Texto histórico")
        db.session.commit()
        db.session.delete(user)
        db.session.commit()
        assert db.session.get(UserProfile, uid) is None
        assert db.session.get(JobPosition, pid) is not None


@pytest.mark.parametrize("kind", ["departments", "positions"])
def test_duplicate_post_is_clear_and_atomic(client, app, kind):
    actor, secret = signin(client, app, role="admin")
    pid, did = catalog(app)[0]
    model = Department if kind == "departments" else JobPosition
    with app.app_context():
        original = db.session.get(model, did if kind == "departments" else pid).name
    response = send(
        client,
        app,
        actor,
        secret,
        "/admin/organization/" + kind,
        {"name": "  " + original.upper() + "  ", "department_id": did},
    )
    assert response.status_code == 409
    assert "Já existe" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(model)) == (
            6 if kind == "departments" else 21
        )


def test_duplicate_on_edit_preserves_name(client, app):
    actor, secret = signin(client, app, role="admin")
    positions = catalog(app)
    first, did = positions[0]
    second, _ = positions[1]
    with app.app_context():
        name = db.session.get(JobPosition, first).name
        original = db.session.get(JobPosition, second).name
    response = send(
        client,
        app,
        actor,
        secret,
        f"/admin/organization/positions/{second}",
        {"name": name, "department_id": did},
    )
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(JobPosition, second).name == original


def test_inactive_department_blocks_reactivation_and_keeps_assignments(client, app):
    actor, secret = signin(client, app, role="admin")
    pid, did = catalog(app)[0]
    send(
        client,
        app,
        actor,
        secret,
        f"/admin/organization/assign/{actor}",
        {"job_position_id": pid, "department_id": did},
    )
    assert (
        send(
            client,
            app,
            actor,
            secret,
            f"/admin/organization/departments/{did}",
            {"action": "deactivate"},
        ).status_code
        == 302
    )
    assert (
        send(
            client,
            app,
            actor,
            secret,
            f"/admin/organization/positions/{pid}",
            {"action": "reactivate"},
        ).status_code
        == 409
    )
    with app.app_context():
        account = db.session.get(User, actor)
        assert account.active and account.role == "admin"
        assert account.profile.job_position_id == pid
        assert account.public_data()["job_position"]
        assert not account.public_data()["job_position_active"]


def test_combined_filters_and_pagination(client, app):
    actor, _ = signin(client, app, role="admin")
    pid, did = catalog(app)[0]
    with app.app_context():
        for number in range(30):
            user = User(
                username=f"collaborator{number:02}", password_hash="not-used", active=number % 2
            )
            user.profile = UserProfile(full_name="Nome Pesquisável", job_position_id=pid)
            db.session.add(user)
        db.session.commit()
    first = client.get("/admin/users?q=collaborator").get_data(as_text=True)
    assert "collaborator24" in first and "collaborator25" not in first
    second = client.get("/admin/users?q=collaborator&page=2").get_data(as_text=True)
    assert "collaborator29" in second and "collaborator00" not in second
    filtered = client.get(
        f"/admin/users?q=Pesquisável&department_id={did}&job_position_id={pid}&active=1&role=user"
    ).get_data(as_text=True)
    assert "collaborator01" in filtered and "collaborator00" not in filtered


def test_user_cannot_change_assignment_through_personal_profile(client, app):
    uid, secret = signin(client, app)
    pid, did = catalog(app)[0]
    other, _ = seed(app, "other_account")
    with app.app_context():
        db.session.get(User, uid).profile = UserProfile(job_position_id=pid)
        db.session.commit()
    response = send(
        client,
        app,
        uid,
        secret,
        "/my-data/edit",
        {
            "username": "alice",
            "full_name": "Titular",
            "user_id": other,
            "job_position_id": pid + 1,
            "department_id": did,
            "job_title": "CEO",
            "role": "admin",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        account = db.session.get(User, uid)
        assert account.role == "user" and account.profile.job_position_id == pid
        assert account.profile.job_title is None
        assert db.session.get(User, other).profile is None


def test_service_revalidates_actor_after_role_revoked(client, app):
    from werkzeug.exceptions import Forbidden

    from app.services.organization_service import assign

    actor, _ = signin(client, app, role="admin")
    pid, did = catalog(app)[0]
    with client.session_transaction() as existing:
        cookie_session = dict(existing)
    with app.test_request_context("/"):
        from flask import session
        from flask_login import current_user

        session.update(cookie_session)
        assert current_user.role == "admin"
        db.session.execute(db.update(User).where(User.id == actor).values(role="user"))
        db.session.commit()
        with pytest.raises(Forbidden):
            assign(actor, {"job_position_id": pid, "department_id": did})


def test_migration_preserves_legacy_profile(app, tmp_path):
    from flask_migrate import upgrade

    from app import create_app

    path = tmp_path / "organization-migration.db"
    migrated = create_app({**app.config, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + path.as_posix()})
    with migrated.app_context():
        upgrade(revision="0004_birth_date")
        db.session.execute(
            db.text(
                "INSERT INTO users(id, username, password_hash) VALUES(1, 'legacy_org', 'historical-hash')"
            )
        )
        db.session.execute(
            db.text(
                "INSERT INTO user_profiles(user_id, full_name, job_title, legacy_age, photo) VALUES(1, 'Nome anterior', 'Cargo sem correspondência', 42, X'010203')"
            )
        )
        db.session.commit()
        upgrade()
        account = db.session.get(User, 1)
        assert account.profile.job_title == "Cargo sem correspondência"
        assert account.profile.photo == b"\x01\x02\x03"
        assert account.profile.legacy_age == 42
        assert account.profile.job_position_id is None
        assert account.password_hash == "historical-hash"
        assert list(path.parent.glob(path.name + ".*.pre-alembic.bak"))
        db.session.remove()
        db.engine.dispose()


def test_csv_export_and_deletion_workflow(client, app):
    from app.models import DeletionRequest
    from app.services.privacy_service import create_deletion_request, export_data, process_request

    actor, secret = signin(client, app, role="admin")
    target, _ = seed(app, "to_delete")
    pid, did = catalog(app)[0]
    assert (
        send(
            client,
            app,
            actor,
            secret,
            f"/admin/organization/assign/{target}",
            {"job_position_id": pid, "department_id": did},
        ).status_code
        == 302
    )
    with app.app_context():
        csv, mime = export_data(target, ["account"], "csv")
        assert "Direção" in csv and "Diretor-Geral (CEO)" in csv
        assert mime == "text/csv" and "totp_secret" not in csv
        create_deletion_request(target)
        rid = db.session.scalar(
            db.select(DeletionRequest.id).where(DeletionRequest.user_id == target)
        )
        process_request(actor, rid, "process")
        process_request(actor, rid, "complete")
        assert db.session.get(User, target) is None
        assert db.session.get(UserProfile, target) is None
        assert db.session.get(JobPosition, pid) is not None
