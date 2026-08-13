import uuid


def test_list_projects_without_session_override_does_not_500():
    # Regression test: the `client` fixture overrides get_session with a plain
    # generator, which masked get_session being wrongly decorated with
    # @contextmanager (FastAPI's Depends() double-wraps that, breaking every
    # real request with AttributeError on '_GeneratorContextManager'). This
    # hits the app exactly as a real deployment would, with no override.
    from fastapi.testclient import TestClient
    from app.db import Base, engine
    from app.main import app

    # Since main.py no longer runs Base.metadata.create_all() at import time
    # (schema creation moved to `alembic upgrade head`, run separately in
    # production/Docker), this test must ensure the schema exists on the
    # default engine's database itself, or it hits a real, table-less
    # sqlite file and fails with "no such table: users" instead of
    # exercising the session-handling behavior it's actually regression
    # testing for.
    Base.metadata.create_all(engine)

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
