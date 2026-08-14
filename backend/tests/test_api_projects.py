import uuid


def test_list_projects_without_session_override_does_not_500(monkeypatch, tmp_path):
    # Regression test: the `client` fixture overrides get_session with a plain
    # generator, which masked get_session being wrongly decorated with
    # @contextmanager (FastAPI's Depends() double-wraps that, breaking every
    # real request with AttributeError on '_GeneratorContextManager'). This
    # hits the app exactly as a real deployment would, with no override.
    from sqlalchemy.orm import sessionmaker
    from app.db import Base, make_engine
    import app.db as db_module

    # main.py no longer runs Base.metadata.create_all() at import time
    # (schema creation moved to `alembic upgrade head`, run separately in
    # production/Docker), so get_session needs a database with the schema
    # already present. Rather than creating the schema on the app's real
    # default engine/database (sqlite:///./testcrafter.db) — which would
    # leave a "stale pre-Alembic" file behind with no alembic_version row,
    # exactly what CONTRIBUTING.md warns against — point SessionLocal at an
    # isolated, temporary database for the duration of this test. This still
    # exercises get_session's real code path (it reads SessionLocal fresh on
    # each call) with no dependency_overrides, which is what this test needs
    # to prove.
    test_engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=test_engine, expire_on_commit=False))

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as real_client:
        email = f"real-deployment-check-{uuid.uuid4()}@example.com"
        token = real_client.post("/auth/register", json={"email": email, "password": "s3cret!"}).json()["access_token"]
        resp = real_client.get("/projects", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


def test_create_and_list_project(authenticated_client):
    resp = authenticated_client.post("/projects", json={"name": "Demo Site", "base_url": "https://example.com"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Demo Site"

    list_resp = authenticated_client.get("/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_create_project_requires_auth(client):
    resp = client.post("/projects", json={"name": "Demo Site", "base_url": "https://example.com"})
    assert resp.status_code == 401


def test_list_projects_only_returns_own_projects(client):
    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    client.post("/projects", json={"name": "A's project", "base_url": "https://a.example.com"}, headers={"Authorization": f"Bearer {token_a}"})

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get("/projects", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 200
    assert resp.json() == []


def test_get_project_returns_owned_project(authenticated_client):
    create_resp = authenticated_client.post("/projects", json={"name": "Demo Site", "base_url": "https://example.com"})
    project_id = create_resp.json()["id"]

    resp = authenticated_client.get(f"/projects/{project_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == project_id
    assert body["name"] == "Demo Site"


def test_get_project_404_for_unknown_id(authenticated_client):
    resp = authenticated_client.get("/projects/999999")
    assert resp.status_code == 404


def test_get_project_404_for_other_users_project(client):
    token_a = client.post("/auth/register", json={"email": "get-a@example.com", "password": "pw"}).json()["access_token"]
    create_resp = client.post("/projects", json={"name": "A's project", "base_url": "https://a.example.com"}, headers={"Authorization": f"Bearer {token_a}"})
    project_id = create_resp.json()["id"]

    token_b = client.post("/auth/register", json={"email": "get-b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get(f"/projects/{project_id}", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404
